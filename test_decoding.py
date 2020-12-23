from TorrentDecode import TorrentDecode, file_read

test_obj = TorrentDecode(file_read('BlackCrowes.torrent'))

print(len(test_obj.info['pieces']))
print(test_obj.get_piece_length(580))