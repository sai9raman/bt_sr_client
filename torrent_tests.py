from nose.tools import *

from torrent import Torrent
from tracker import TorrentTracker, AnnounceDecodeError


def test_torrent_peer():

	class MockMetainfo():
		def __init__(self):
			self.info = {
			'pieces' : []
			}

	metainfo = MockMetainfo()

	torrent = Torrent(None, metainfo)	 # No connection manager given 

	pd1 = {'ip':'1.1.1.1', 'port':3}
	pd2 = {'ip':'1.1.2.1', 'port':7}

	p1a = torrent.add_peer(pd1)
	(assert_is_not_none(p1a))
	p1b = torrent.add_peer(pd1)
	(assert_is_not_none(p1a))

	assert_equal(id(p1a),id(p1b))  # id function returns the memory id of where an object is stored 

	p2 = torrent.add_peer(pd2)
	assert_is_not_none(p2)
	assert(len(torrent.peers)==2)
	print('finished')

	
test_torrent_peer()
