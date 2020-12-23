import logging
import struct
import bitarray
import random

from config import CONFIG


log = logging.getLogger(__name__)

class TorrentPeer():

	""" This is a class that manages the operation relating to the interactions with a specific peer 
		The actions will relate to the upload and download of a torrent 
	"""

	def __init__(self, torrent, ip, port, peer_id=None):

		self.torrent = torrent 
		self.ip = ip
		self.peer_id = peer_id
		self.port = port 
		
		self.conn = None 
		self.recv_buffer = b''

		self.is_started = False 
		self.conn_failed = False 
		self.am_choking = True 
		self.am_interested = False 
		self.peer_choking = True 
		self.peer_interested = False 

		self.peer_pieces = [False for _ in range(len(self.torrent.metainfo.info['pieces']))]
		self.requested_piece = None 

	def __repr__(self):
		return ('TorrentPeer(ip={ip}, port={port})'.format(**self.__dict__))

	def connect(self):
		self.torrent.conn_man.connect_peer(self)

	def run_download(self):

		""" For a given peer, manage the flow of the downloading process - handshake, interest, request / disconnect, obtain """

		if not self.is_started : # initiate contact 
			self.send_handshake()

		elif self.peer_choking: # show interest
			self.send_message('interested')

		elif self.requested_piece is not None:  # meaning we already requested a piece 
			pass # then patiently wait for it 

		else: # ask for a piece 

			try:
				piece = self._choose_next_piece()

			except PeerNoUnrequestedPiecesError: # if  there are no pieces that we have not requested from this peer, then peer has been fully utilized. Move on
				self.conn.disconnect()
				self.torrent.handle_peer_stopped(self)
				return 

			self.requested_piece = piece 
			self.torrent.piece_requests[piece].append(self) # add the peer to the list of peers from which that piece has been requested
			self.request_next_block(piece,None)


	def _choose_next_piece(self):

		""" For a given peer, which piece to request from that peer """

		num_pieces = len(self.torrent.metainfo.info['pieces'])

		for i in range(num_pieces):
			 # Pick a piece that 1. is not completed 2. is not already requested and 3. is available with that peer
			if (not self.torrent.complete_pieces[i] and not self.torrent.piece_requests[i] and self.peer_pieces[i]):
				return i

		candidates = []
		for i in range(num_pieces):
			if (not self.torrent.complete_pieces[i] and self.peer_pieces[i]):
				candidates.append(i)

		if not candidates:
			raise PeerNoUnrequestedPiecesError

		return random.choice(candidates)

	# ========= Workflow management functions below - Handle functions ========= #

	def handle_connection_made(self,conn):
		
		self.conn = conn
		log.info('%s: handle_connection_made ' % self) # log the information that a conn was made with this peer 
		self.run_download()

	def handle_connection_failed(self):

		log.info('%s: handle_connection_failed ' % self) # log the information that a conn with this peer has failed
		self.conn_failed = True
		self.conn = None
		self.torrent.handle_peer_stopped(self)

	def handle_connection_lost(self):

		log.info('%s: handle_connection_lost ' % self) # log the information that a conn with this peer is lost
		self.conn_failed = True
		self.conn = None
		self.torrent.handle_peer_stopped(self)


	def handle_data_received(self, recv_data):
		
		# TODO Understand the point of this function better 
		""" 
		Current Understanding - this function directs the  parsing and reading job to the correct function 
		between message and handshake 
		"""

		data = self.recv_buffer + recv_data	#adding the b'' to the data string
		
		while data:
			if not self.is_started: # which means that the data that was received was pertaining to the handshake 
				nbytes = self.parse_handshake(data)
			else:
				nbytes = self.parse_message(data)

			if nbytes ==0:
				break 
			
			data = data[nbytes:] # updating data to be an empty string to be able to exit the while loop 
			#TODO - understand this better

		self.recv_buffer = data # setting the recv buffer back to empty string 


	def handle_torrent_completed(self):
		
		if self.conn:
			self.conn.disconnect()
		self.requested_piece = None


	def handle_handshake_ok(self):

		self.run_download()

	def handle_unchoke(self):

		self.run_download()

	def handle_keepalive(self):
		pass 


	# ========= Message Management Functions below ========= #

	def write_message(self, msg):
		
		if self.conn:
			self.conn.write(msg)

	def send_handshake(self):

		log.debug('%s: send_handshake' % self)
		msg = self.build_handshake(self.torrent.metainfo.info_hash,CONFIG['peer_id'])

		self.write_message(msg)


	def send_message(self, msg_type, **params):

		if not self.is_started:
			raise PeerConnectionError('Attempted to send message before handshake')

		log.debug('%s: send_message: type=%s, params=%s' % (self,msg_type,params))

		if msg_type=='request' and self.peer_choking:
			log.debug('Attempted to send message to choking peer')
			return

		msg = self.build_message(msg_type,**params)

		self.write_message(msg)


	def request_next_block(self, piece_index, begin):
		
		piece_length = self.torrent.metainfo.get_piece_length(piece_length)

		begin = 0 if begin is None else begin + CONFIG['block_length']
		# TODO: Understand why it is begin + block_length
		
		block_length = min(piece_length-begin, CONFIG['block_length'])

		self.send_message('request', index=piece_index, begin=begin, length=block_length)
		

	# ========= Message Management SUB-Functions below ========= #

	def parse_handshake(self,data):
		""" Once data is received, if the message recd. is supposed to be a handshake, then this function 
		looks in to it. 
		The handshake is a required message and must be the first message transmitted by the client. It is (49+len(pstr)) bytes long.

		handshake: <pstrlen><pstr><reserved><info_hash><peer_id>

		"""

		pstrlen = int(data[0]) 
		handshake_data = data[1:49+pstrlen]
		handshake = self.decode_handshake(pstrlen, handshake_data)
		
		if handshake['pstr'] != 'BitTorrent protocol':
			raise PeerProtocolError('Unrecognized protocol')

		# Now, if, handshake is all good

		self.is_started = True
		log.debug('%s: received_handshake' % self)
		self.handle_handshake_ok() # initiates the run download command 

		return (1+len(handshake_data))

	def parse_message(self, data):
		
		""" 
		This function parses a message and returns the no. of bytes that the message consumes
		All of the remaining messages in the protocol take the form of 
			<length prefix><message ID><payload>. 
		The length prefix is a four byte big-endian value. The message ID is a single decimal byte. 
		The payload is message dependent.
		"""

		nbytes = 0 

		if len(data) < 4:
			return nbytes

		length_prefix = struct.unpack('!L',data[:4])[0] 
		#TODO: Understand Struct and unpack a little better. Syntax: struct.unpack(format,buffer)
		nbytes+=4

		if length_prefix == 0:
			log.debug('%s: receive_message: keep-alive' % self)
			return nbytes

		if nbytes+length_prefix>len(data):
			# means that incomplete message was received, so can raise error
			return 0 

		msg_dict = self.decode_message(data[nbytes:nbytes+length_prefix])
		nbytes+=length_prefix
		self.handle_message(msg_dict)

		return nbytes


	def handle_message(self, msg_dict):

		""" 
		Core Function: responds and acts according to the message received from the peer 
		MEAT of this entire project 
		"""

		msg_id = msg_dict['msg_id']
		payload = msg_dict['payload']

		msg_types = ['choke','unchoke','interested','not_interested','have',
					'bitfield','request','piece','cancel','port']

		msg_type = msg_types[msg_id]


		log.debug('%s: receive_msg: id=%s type=%s payload=%s%s' % (self, msg_id,msg_type,
			''.join('%02X' % v for v in payload[:40]),  '...' if len(payload)>64 else '' ) )
		# the 4th and the 5th string specifier log the payload string. 
		# 4th
		# %02x means if your provided value is less than two digits then 0 will be prepended.
		# the capital X means Hex and that the digits above 9 will be in upper-case 
		# We are joining all the payload values and logging them 
		# 5th
		# if there are more than 64 payload length, then we print "..." 

		if msg_id == 0:
			assert(msg_type=='choke')
			self.peer_choking = True

		elif msg_id == 1: 
			assert(msg_type=='unchoke')
			self.peer_choking = False
			self.handle_unchoke()

		elif msg_id == 2:
			assert(msg_type=='interested')
			self.peer_interested = True

		elif msg_id == 3:
			assert(msg_type=='not_interested')
			self.peer_interested = False

		elif msg_id == 4:
			assert('msg_type'=='have')
			(index,) = struct.unpack('!L',payload)
			self.peer_pieces[index] = True

		elif msg_id == 5:
			assert('msg_type'=='bitfield')
			bitfield = payload 
			ba = bitarray.bitarray(endian='big')
			ba.frombytes(bitfield)
			num_pieces = len(self.torrent.metainfo.info['pieces'])

			# note: the bitfield message is only sent once after the handshake 
			self.peer_pieces = ba.tolist()[:num_pieces] 
			# through this we are storing the information as to which pieces the peer has 

		elif msg_id == 6:
			assert('msg_type'=='request')
			 # TODO - confirm if understanding is right 
			 # since the peer is requesting for a piece, we don't care, since we are building a one way download client 

		elif msg_id == 7:
		 	assert('msg_type'=='piece')
		 	(index,begin) = struct.unpack('!LL',payload[:8])
		 	block = payload[8:]
		 	self.torrent.handle_block(self, index, begin, block)

		elif msg_id == 8:
	 		assert('msg_type'=='cancel')

		elif msg_id == 9:
 			assert('msg_type'=='port')

		else:
			raise PeerProtocolMessageTypeError('Unrecognized message id: %s'% msg_id)


	# ========= Static Functions below ========= #

	@staticmethod
	def build_handshake(info_hash, peer_id):
		""" 
		A very COOL way to send a handshake in Bytes form (using Struct to pack it up like that)
		Reqd. format of the message: <pstrlen><pstr><reserved><info_hash><peer_id>
		pstrlen = 19 (length of pstr) [1byte]
		pstr = BitTorrent protocol 
		reserved = 8 bytes of zeros 
		info_hash = 20bytes 
		peer_id = 20bytes 
		
		Total size of message = 1 + len(pstr) + 8 + 20 + 20 = 49 + len(pstr)
		
		"""

		pstr = b'BitTorrent protocol'
		fmt = "!B%ds8x20s20s" % len(pstr)
		msg = struct.pack(fmt, len(pstr), pstr, info_hash, peer_id)

		return msg

	@staticmethod
	def build_message(msg_type, **params):

		""" 
		Message Form: <length prefix><message ID><payload>

		

		Payload Form: 
		None of the messages carry a payload other than the request message
		Request message payload : <len=0013><id=6><index><begin><length>
		index= integer 
		begin= integer
		length= integer
	

		"""

		msg_id = None
		payload = b''

		if msg_type == 'choke':
			msg_id = 0

		elif msg_type == 'unchoke':
			msg_id = 1

		elif msg_type == 'interested':
			msg_id = 2

		elif msg_type == 'not_interested':
			msg_id = 3

		elif msg_type == 'have':
			msg_id = 4

		elif msg_type == 'bitfield':
			msg_id = 5

		elif msg_type == 'request':
			msg_id = 6
			payload = struct.pack('!LLL', params['index'],params['begin'],params['length'])

		elif msg_type == 'piece':
			msg_id = 7

		elif msg_type == 'cancel':
			msg_id = 8

		elif msg_type == 'port':
			msg_id = 9

		else:
			raise PeerProtocolMessageTypeError('Unrecognized message type: %s' % msg_type)


		length_prefix = 1 + len(payload) # the additional 1 byte is added for the length of the msg_id
		fmt = '!LB%ds' % len(payload)
		msg = struct.pack(fmt, length_prefix, msg_id, payload)

		return msg

		@staticmethod
		def decode_message(data):
			msg_id = int(data[0])
			payload = data[1:]

			return {'msg_id':msg_id, 'payload':payload}


	class AnnounceFailureError(Exception):
		pass

	class AnnounceDecodeError(Exception):
		pass

	class PeerConnectionError(Exception):
		pass

	class PeerProtocolError(Exception):
		pass

	class PeerProtocolMessageTypeError(Exception):
		pass

	class PeerNoUnrequestedPiecesError(Exception):
		pass






