from mitmproxy import ctx
import json
import struct
import gzip
import blackboxprotobuf
import os

CONFIG_DIR = os.path.expanduser('~') + '/.teenager/bilibili'

def load_config_file(path):
	data = []
	with open(path) as f:
		data = f.readlines()
	data = list(map(str.strip, data))
	data = list(filter(lambda x: len(x) > 0, data))
	return data

block_uid = load_config_file(CONFIG_DIR + '/uid')
print('Block UID: {0}'.format(block_uid))
block_user = load_config_file(CONFIG_DIR + '/user')
print('Block USER: {0}'.format(block_user))
block_word = load_config_file(CONFIG_DIR + '/word')
print('Block WORD: {0}'.format(block_word))

def is_allowed_uid(i):
	return i not in block_uid

def is_allowed_user(s):
	return s not in block_user

def is_allowed_str(s):
	t = s.lower().replace(' ', '')
	for w in block_word:
		x = w.lower()
		if t.find(x) >= 0:
			return False
	return True

def bili_grpc_fix_types(types):
	for k, v in types.items():
		if isinstance(v, dict):
			types[k] = bili_grpc_fix_types(v)
		if v == 'bytes':
			types[k] = 'str'
	return types

def bili_grpc_decode(content):
	compressed, size = struct.unpack('>BI', content[0:5])
	data = content[5:]
	if size != len(data):
		return None
	if compressed != 0:
		data = gzip.decompress(data)
	# FIXME
	#_, types = blackboxprotobuf.decode_message(data)
	#types = bili_grpc_fix_types(types)
	#return blackboxprotobuf.decode_message(data, types)
	return blackboxprotobuf.decode_message(data)

def bili_grpc_encode(d, t):
	body = gzip.compress(blackboxprotobuf.encode_message(d, t))
	head = struct.pack('>BI', 1, len(body))
	return head + body

def bili_filter_feed(item):
	perm = True
	try:
		# 广告
		ad_info = item.get('ad_info')
		if ad_info != None:
			# print('Block feed: ad: {0}'.format(item))
			return False
		# 竖屏
		goto = item.get('goto')
		if goto == 'vertical_av':
			# print('Block feed: vv: {0}'.format(item))
			return False
		bvid = item.get('bvid')
		args = item.get('args')
		# up主
		if args != None:
			uid = args.get('up_id')
			if uid != None:
				perm &= is_allowed_uid(uid)
			user = args.get('up_name')
			if user != None:
				perm &= is_allowed_user(user)
		owner = item.get('owner')
		if owner != None:
			uid = owner.get('mid')
			if uid != None:
				perm &= is_allowed_uid(uid)
			user = owner.get('name')
			if user != None:
				perm &= is_allowed_user(user)
		title = item['title']
		perm &= is_allowed_str(title)
		desc = item.get('talk_back')
		if desc != None:
			perm &= is_allowed_str(desc)
		# 偶尔有tag在这些中间
		hint = ['dislike', 'dislike_reasons_v2', 'dislike_reasons_v3', 'three_point', 'three_point_v2', 'three_point_v3']
		for n in hint:
			data = item.get(n)
			if data != None:
				perm &= is_allowed_str(json.dumps(data))
		if perm == False:
			print('Blocked feed: {0}:{1}:{2}:{3}'.format(uid, user, bvid, title))
		return perm
	except KeyError as e:
		print(e)
		print('bili_filter_feed: {0}'.format(item))
	return perm

def bili_filter_search_live(item):
	perm = True
	try:
		user = item.get('name')
		if user != None:
			perm &= is_allowed_user(user)
		title = item.get('title')
		if title != None:
			perm &= is_allowed_str(title)
		area = item.get('area_v2_name')
		if area != None:
			perm &= is_allowed_str(area)
		tags = item.get('tags')
		if  tags != None:
			perm &= is_allowed_str(tags)
		if perm == False:
			print('Blocked search/live: {0} - {1}'.format(user, title))			
	except KeyError as e:
		print(e)
		print('bili_filter_seach_live: {0}'.format(item))
	return perm

def bili_filter_search_type(item):
	perm = True
	try:
		user = item.get('name')
		if user != None:
			perm &= is_allowed_user(user)
		title = item.get('title')
		if title != None:
			perm &= is_allowed_str(title)
		desc = item.get('desc')
		if desc != None:
			perm &= is_allowed_str(desc)
		if perm == False:
			print('Blocked search/type: {0} - {1}'.format(user, title))			
	except KeyError as e:
		print(e)
		print('bili_filter_search_type: {0}'.format(item))
	return perm

def bili_filter_search(item):
	perm = True
	try:
		user = item.get('author')
		if user != None:
			perm &= is_allowed_user(user)
		title = item['title']
		perm &= is_allowed_str(title)
		link_type = item.get('linktype')
		# 频道
		if link_type == 'channel':
			for it in item['items']:
				title = it['title']
				perm &= is_allowed_str(title)
		if perm == False:
			print('Blocked search: {0} - {1}'.format(user, title))			
	except KeyError as e:
		print(e)
		print('bili_filter_search: {0}'.format(item))
	return perm

def bili_filter_space(item):
	perm = True
	try:
		user = item.get('author')
		if user != None:
			perm &= is_allowed_user(user)
		title = item.get('title')
		if title != None:
			perm &= is_allowed_str(title)
	except KeyError as e:
		print(e)
		print('bili_filter_space: {0}'.format(item))
	return perm

def bili_filter_related_videos(item):
	perm = True
	try:
		title = item.get('3')
		if title != None:
			title = title.decode('utf-8')
			perm &= is_allowed_str(title)
		owner = item.get('4')
		if owner != None:
			uid = owner.get('1')
			if uid != None:
				perm &= is_allowed_uid(uid)
			user = owner.get('2')
			if user != None:
				user = user.decode('utf-8')
				perm &= is_allowed_user(user)
		if perm == False:
			print("Blocked: bili_filter_related_videos: {0}: {1}".format(user, title))
	except KeyError as e:
		print(e)
		print('bili_filter_related_videos: {0}'.format(item))
	return perm

def bili_filter_view(data):
	data['10'] = list(filter(bili_filter_related_videos, data['10']))
	return data

def response(flow) -> None:
	if flow.request.pretty_host == 'app.bilibili.com':
		# 推荐
		if flow.request.path.startswith('/x/v2/feed/index'):
			text = flow.response.text
			data = json.loads(text)
			item = data['data'].get('items')
			if item != None:
				data['data']['items'] = list(filter(bili_filter_feed, item))
			flow.response.text = json.dumps(data)
		# 搜索 - 直播
		if flow.request.path.startswith('/x/v2/search/live?'):
			text = flow.response.text
			data = json.loads(text)
			live_room = data['data']['live_room']
			items = live_room.get('items')
			if items != None:
				data['data']['live_room']['items'] = list(filter(bili_filter_search_live, items))
			flow.response.text = json.dumps(data)
		# 搜索 - 专栏
		if flow.request.path.startswith('/x/v2/search/type?'):
			text = flow.response.text
			data = json.loads(text)
			item = data['data'].get('items')
			if item != None:
				data['data']['items'] = list(filter(bili_filter_search_type, item))
			flow.response.text = json.dumps(data)
		# 搜索
		if flow.request.path.startswith('/x/v2/search?'):
			text = flow.response.text
			data = json.loads(text)
			# NOT spelling miss!
			item = data['data'].get('item')
			if item != None:
				data['data']['item'] = list(filter(bili_filter_search, item))
			flow.response.text = json.dumps(data)
		# 主页
		if flow.request.path.startswith('/x/v2/space?'):
			text = flow.response.text
			data = json.loads(text)
			item = data['data']['archive'].get('item')
			if item != None:
				data['data']['archive']['item'] = list(filter(bili_filter_space, item))
			flow.response.text = json.dumps(data)
	if flow.request.pretty_host == 'grpc.biliapi.net':
		# 相关视频
		if flow.request.path == '/bilibili.app.view.v1.View/View':
			d, t = bili_grpc_decode(flow.response.raw_content)
			d = bili_filter_view(d)
			flow.response.raw_content = bili_grpc_encode(d, t)
