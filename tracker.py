import requests
import bencodepy
import logging 
import struct


from config import CONFIG

log = logging.getLogger(__name__)

class TorrentTracker():
	""" a class that manages a tracker that allows us to 
	connect to the torrent and make and receive requests """

	def __init__(self, torrent, announce):
		self.torrent = torrent
		self.announce = announce
		self.tracker_id = None


	def send_announce_request(self):
		""" This function seeks to send an announce request to the server, 
		obtains the response and passes control to the function that can handle the response """
		http_resp = requests.get(self.announce, {
			'info_hash': self.torrent.metainfo.info_hash,
			'peer_id': CONFIG['peer_id'],
			'port':6881,
			'uploaded':0,
			'downloaded':0,
			'left': str(self.torrent.metainfo.info['length'])
		})
		self.handle_announce_response(http_resp)

	def handle_announce_response(self, http_resp):


		resp = bencodepy.decode(http_resp.text.encode('latin-1')) 
		#Latin-1 (also called ISO-8859-1), which is technically the default for the Hypertext Transfer Protocol (HTTP)
		
		d = self.decode_announce_response(resp)


		for peer_dict in d['peers']:
			if peer_dict['ip'] and peer_dict['port']>0:
				self.torrent.add_peer(peer_dict) 


	@classmethod
	def decode_announce_response(cls,resp):
		d={}

		if b'failure reason' in resp:
			raise AnnounceFailureError(resp[b'failure reason'].decode('utf-8'))

		d['interval'] = int(resp[b'interval'])
		d['complete'] = int(resp[b'complete']) if b'complete' in resp else None
		d['incomplete'] = int(resp[b'incomplete']) if b'incomplete' in resp else None

		try:
			d['tracker_id'] = resp[b'tracker_id'].decode('utf-8')
		except KeyError:
			d['tracker_id'] = None

		raw_peers = resp[b'peers']

		if isinstance(raw_peers,list):
			# log.info('list peers')
			d['peers'] = cls.decode_dict_model_peers(raw_peers)
		elif isinstance(raw_peers,bytes):
			# log.info('bytes peers')
			d['peers'] = cls.decode_binary_model_peers(raw_peers)
		else:
			raise AnnounceDecodeError('Invalid peers format: %s' % raw_peers)

		return d 

	@staticmethod
	def decode_dict_model_peers(raw_peers_dicts):
		peer_dict_list = []
		for d in raw_peers_dicts: 
			peer_dict_list.append({
				'ip' : d[b'ip'].decode('utf-8'),
				'port' : d[b'port'],
				'peer_id' : d.get(b'peer_id') # get() method: if Key is missing then returns "None" instead of throwing keyError
				})

		return peer_dict_list


	@staticmethod
	def decode_binary_model_peers(raw_peers_bytes):
		fmt = '!BBBBH'
		fmt_size = struct.calcsize(fmt)
		if len(raw_peers_bytes) % fmt_size !=0:
			raise AnnounceDecodeError('Binary Model peers length error')

		peers = [struct.unpack_from(fmt,raw_peers_bytes,offset=ofs) 
				for ofs in range(0,len(raw_peers_bytes),fmt_size)]

		peer_dict_list = [{
		'ip': '%d.%d.%d.%d' % p[:4],
		'port':int(p[4])
		}
		for p in peers ]

		return peer_dict_list


class AnnounceFailureError(Exception):
	pass
class AnnounceDecodeError(Exception):
	pass
