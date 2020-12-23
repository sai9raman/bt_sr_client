import bencodepy
import voluptuous as vol
import hashlib
import os

# Read the torrent file using this function 
def file_read(filepath):
	f = open(filepath,"rb")
	return f.read()

class TorrentMetainfo():
	""" 
		This class extracts the various attributes that are needed, from the Torrent file
	"""
	def __init__(self,torrent_file_content):

		if not torrent_file_content:
			raise "Empty Torrent File - cannot parse"

		try: #tries to decode (bencode) the contents of the torrent file 
			content = bencodepy.decode(torrent_file_content)
		except:
			raise "Unable to decode file"

		# Verifying the encoding of the decoded file and making sure its utf-8
		text_encoding = content[b'encoding'] 
		if not text_encoding or text_encoding.decode("utf-8").lower()!="utf-8":
			raise "Torrent file contents not encoded in the correct format"

		# 1 -- URL  	
		#  Extract the URL for requesting the files from 
		self.announce = content[b'announce'].decode("utf-8")

		# Validate the URL 
		try:
			vol.Url()(self.announce)
		except:
			raise f'Invalid Url {self.announce}'

			
		info_dict = content[b'info']
		
		# 2 --  Name of the torrent 
		self.name = info_dict[b'name'].decode("utf-8")
		
		# 3 --  Hash of the bencoded info dictionary 
		self.info_hash = hashlib.sha1(bencodepy.encode(info_dict)).digest()
		
		# 4 --  Info dictionary parsed into an "Info" dictionary that contains
			# a) piece length - length of each piece 
			# b) pieces - the sha encoded pieces themselves 
			# c) format - single / multiple 
			# d) length - (combined) length of the file(s)
			# c) files - NONE if single file, else
				# i] path - os path to each file
				# ii] length - length of each sub-file


		self.info = self.parse_info_dict(info_dict)


	def parse_info_dict(self,info_dict):

		# 4 --  Info dictionary parsed into an "Info" dictionary that contains
			# a) piece length - length of each piece  [except this doesn't apply to last piece]
			# b) pieces - the sha encoded pieces themselves 
			# c) format - single / multiple 
			# d) length - (combined) length of the file(s) [piece_length * #pieces  = length]
			# c) files - NONE if single file, else
				# i] path - os path to each file
				# ii] length - length of each sub-file


		info = {}

		info['piece_length'] = info_dict[b'piece length']

		SHA_LEN  = 20
		sha_pieces = info_dict[b'pieces']

		info['pieces']=[]
		for i in range(0,len(sha_pieces),SHA_LEN):
			info['pieces'].append([sha_pieces[i:i+SHA_LEN]])

		try:
			files = info_dict[b'files']
		except:
			files = None
			info['format']='SINGLE_FILE'
			info['files']= 'NONE'
			info['length']=info_dict[b'length']

		if not files: 
			info['format']='SINGLE_FILE'
			info['files']= 'NONE'
			info['length']=info_dict[b'length']

		else: 
			info['format']='MULTIPLE_FILE'
			info['files']=[]
			for file_dict in files:
				path_seg = [p.decode("utf-8") for p in file_dict[b'path']]
				info['files'].append({
					'length': file_dict[b'length'],
					'path': os.path.join(*path_seg)
					})
			info['length']=sum(f['length'] for f in info['files'])

		return info
		

	def get_piece_length(self,indx):

		num_pieces = len(self.info['pieces'])
		if indx == num_pieces-1:
			piece_length = self.info['length'] - ( (num_pieces-1)*self.info['piece_length'] )
		else: 
			piece_length = self.info['piece_length']

		return piece_length
