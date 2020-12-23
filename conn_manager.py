"""
This file defines the classes related to making and managing the concurrent peer network connections

For the time being, Twisted is being used to perform this management 

TODO: This process needs to be better understood

"""

import logging 
from twisted.internet import protocol, reactor

#========== TWISTED Approach ===========#

class PeerConnectionProtocol(protocol.Protocol):

	def connectionMade(self):
		self.factory.peer.handle_connection_made(self)

	def dataReceived(self, data):
		self.factory.peer.handle_data_received(data)

	def connectionLost(self, reason):
		pass

	def write(self, data):
		self.transport.write(data)

	def disconnect(self):
		self.transport.lostConnection()


class PeerConnectionFactory(protocol.ClientFactory):

	protocol = PeerConnectionProtocol # TODO: if this is an object that is created, why is there no "()" being used?

	def __init__(self, peer):
		self.peer = peer

	def clientConnectionFailed(self, connector, reason):
		self.peer.handle_connection_failed()

	def clientConnectionLost(self, connector, reason):
		self.peer.handle_connection_lost()


class ConnectionManagerTwisted():
	
	@staticmethod
	def connect_peer(peer):
		f = PeerConnectionFactory(peer)
		reactor.connectTCP(peer.ip, peer.port, f)

	@staticmethod
	def start_event_loop():
		reactor.run()

	@staticmethod
	def stop_event_loop():
		reactor.stop()

	



