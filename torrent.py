import logging 
import hashlib

from config import CONFIG
from peer import TorrentPeer 
from tracker import TorrentTracker

log = logging.getLogger(__name__)

class Torrent():
	"""
	This class represents the overall workflow relating to what needs to be done with the torrent 
	from the beginning to the completion
	"""

	def __init__(self, conn_man, metainfo, on_completed_torrent=None, on_completed_piece=None):
		"""
		Args: 
			conn_man - connection manager for peer connections
			metainfo - contains the decoded information from the torrent file 
			on_completed_torrent - a function that does the activities after torrent donwload is completed  
			on_completed_piece - a function that does the activities after a piece of the torrent is downloaded

		"""
		self.metainfo = metainfo
		self.conn_man = conn_man

		self.active_peers = []
		self.peers = []
		self.tracker = None
		self.is_complete = False 

		self.on_completed_torrent = on_completed_torrent
		self.on_completed_piece = on_completed_piece

		self.piece_blocks = [ [] for _ in self.metainfo.info['pieces'] ] # array that stores the received blocks of an in-progress piece
		self.piece_requests = [ [] for _ in self.metainfo.info['pieces'] ] # array that stores which pieces have been requested 

		 # list with No elements to begin with -- but stores which pieces have been completed 
		self.complete_pieces = [ None for _ in self.metainfo.info['pieces'] ]


	def start_torrent(self):

		self.tracker = TorrentTracker(self,self.metainfo.announce)
		self.tracker.send_announce_request()

		for peer in self.peers[:CONFIG['max_peers']]: 
			peer.connect()


	def add_peer(self,peer_dict):
		""" add a peer to the torrent download pipeline - IF not already present """
		peer = self.find_peer(**peer_dict)

		if peer: 
			return peer 

		peer = TorrentPeer(self,**peer_dict)
		self.peers.append(peer)

		return peer

	def find_peer(self, ip, port, **kwargs):

		for peer_list in (self.active_peers, self.peers): 
			for v in peer_list:
				if v.ip == ip and v.port == port:
					return v

		return None

	def handle_block(self, peer, piece_index, begin, block):

		""" 
		Didn't completely understand this function - where are we requesting the current block?
		"""

		if self.complete_pieces[piece_index]: # implies piece already completed
			return

		for v in self.piece_blocks[piece_index]:

			if v[0] == begin: #TODO: Understand this 
				# already got the block 
				peer.request_next_block(piece_index, begin)
				return 

		# since we haven't gotten the block yet
		self.piece_blocks[piece_index].append((begin, block))
		expected_length = self.metainfo.get_piece_length(piece_index)
		piece_length = sum(len(v[1]) for v in self.piece_blocks[piece_index])

		if piece_length == expected_length:
			self.handle_completed_piece(peer, piece_index)
		else:
			peer.request_next_block(piece_index, begin)


	def handle_completed_piece(self, peer, piece_index):

		if self.complete_pieces[piece_index] is not None: 
			log.warning('Piece already completed: %s' % piece_index)
			return 

		self.piece_blocks[piece_index].sort(key = lambda v: v[0]) # sorting this piece blocks array by the 0th column elemts 

		block = [ v[1] for v in self.piece_blocks[piece_index] ] # getting a sorted list of blocks 

		# a byteArray kinna representation for the piece 
		piece = bytes( v for block in blocks for v in block ) 

		# sha1 encoding the piece bytearray
		piece_sha = hashlib.sha1(piece).digest()

		# the already encrypted sha for the piece 
		canonical_sha = self.metainfo.info['pieces'][piece_index]

		if piece_sha != canonical_sha:
			raise TorrentPieceError('Piece %d sha mismatch' % piece_index)

		self.complete_pieces[piece_index] = piece
		self.piece_blocks[piece_index] = None # this array of received blocks is only for in-progress piece; since this piece is completed, we no longer need it

		# Clearing the piece related  bookkeeping on Peers and torrent 

		for p in self.piece_requests[piece_index]:
			if p.requested_piece == piece_index:
				p.requested_piece = None

			if p != peer: # pending request to some other peer for this piece 
				# ideally want to cancel
				pass 

			self.piece_requests[piece_index] = None 
			log.debug('handle_completed_piece: %d' % piece_index)

			if self.on_completed_piece:
				self.on_completed_piece(self)

			peer.run_download() # initiate the download for the next piece with this peer

			if not any(v is None for v in self.complete_pieces):
				self.handle_completed_torrent()


	def handle_completed_torrent(self):

		log.info('%s: handle_completed_torrent' % (self))

		self.is_complete=True

		data = bytes(v for piece in self.complete_pieces for v in piece)

		for p in self.peers:
			p.handle_torrent_completed() # function disconects from those peers 

		if self.on_completed_torrent: 
			self.on_completed_torrent(self, data)

	def handle_peer_stopped(self, peer):

		""" 
		This function is used when a peer fails, or has been fully leached from; 
		initiates the start with a new peer 
		""" 

		if self.is_complete: #torrent download is over 
			return

		num_active = sum(1 for p in self.peers if p.is_started and not p.conn_failed)

		if num_active >= CONFIG['max_peers']:
			return # TODO: understand, why we are allowing active peers to be over max peers 

		for p in self.peers[CONFIG['max_peers']:]: # for all peers greater than 8 (max # peers)
			
			if p.conn or p.is_started or p.conn_failed: #these peers have already been tried to connect to
				continue 
			log.info('handle_peer_stopped: starting new peer: %s' % p)
			p.connect()
			break

	def get_progress_string(self):

		num_complete = sum(v is not None for v in self.complete_pieces)
		num_pieces = len(self.complete_pieces)

		pct_complete = 100.0 * (num_complete/num_pieces)

		return ('%s / %s (%02.1f%%) complete' % (num_complete,num_pieces,pct_complete))



class TorrentPieceError(Exception):
	pass















