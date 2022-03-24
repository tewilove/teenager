from mitmproxy import ctx
import json
import struct
import gzip
import blackboxprotobuf
import os
import pprint
import re

CONFIG_DIR = os.path.expanduser('~') + '/.teenager/bilibili'

def load_config_file(path):
	data = []
	with open(path) as f:
		data = f.readlines()
	data = list(map(str.strip, data))
	data = list(filter(lambda x: len(x) > 0, data))
	return data

def is_none(v):
	return v == None

def is_allowed_uid(i):
	block_uid = load_config_file(CONFIG_DIR + '/uid')
	return i not in block_uid

def is_allowed_string(s, blacklist):
	if s == None:
		return True
	t = s.lower().replace(' ', '')
	for w in blacklist:
		x = w.lower()
		if t.find(x) >= 0:
			return False
	for e in blacklist:
		try:
			m = re.search(e, s)
			if m != None:
				return False
		except:
			continue
	return True

def is_allowed_user(s):
	blacklist = load_config_file(CONFIG_DIR + '/user')
	return is_allowed_string(s, blacklist)

def is_allowed_text(s):
	blacklist = load_config_file(CONFIG_DIR + '/word')
	return is_allowed_string(s, blacklist)

def is_allowed_uploader(val):
	if val == None:
		return True
	# args格式
	if not is_allowed_uid(val.get('up_id')):
		return False
	if not is_allowed_user(val.get('up_name')):
		return False
	# owner格式
	if not is_allowed_uid(val.get('mid')):
		return False
	if not is_allowed_user(val.get('name')):
		return False
	# 相关视频格式
	if not is_allowed_uid(val.get('1')):
		return False
	user = val.get('2')
	if isinstance(user, bytes):
		user = user.decode('utf-8')
	if not is_allowed_user(user):
		return False
	return True

def is_allowed_goto(val):
	return val != 'vertical_av'

def is_allowed_search_channel(val):
	if val != None:
		for it in val:
			if not is_allowed_text(it['title']):
				return False
	return True

def bili_filter_list(name, data, rule):
	result = []
	for item in data:
		wanted = True
		for f in rule:
			field = list(f.keys())[0]
			check = list(f.values())[0]
			value = item.get(field)
			if isinstance(value, bytes):
				value = value.decode('utf-8')
			wanted &= check(value)
			if wanted == False:
				break
		if wanted:
			result.append(item)
		else:
			print("{0}: dropped: {1}".format(name, item))
	return result

def bili_filter_dict(name, data, rule):
	for k, v in rule.items():
		n = data.get(k)
		if isinstance(v, dict) and isinstance(n, dict):
			n = bili_filter_dict(name, n, v)
		elif isinstance(v, list) and isinstance(n, list):
			print("{0}: before filter: {1}".format(name, len(n)))
			n = bili_filter_list(name, n, v)
			print("{0}: after filter: {1}".format(name, len(n)))
		data[k] = n
	return data

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

def bili_filter_json(name, flow, rule):
	data = json.loads(flow.response.text)
	if isinstance(rule, list):
		for r in rule:
			data = bili_filter_dict(name, data, r)
	else:
		data = bili_filter_dict(name, data, rule)
	flow.response.text = json.dumps(data)

def bili_filter_grpc(name, flow, rule):
	data, template = bili_grpc_decode(flow.response.raw_content)
	#pprint.pprint(data)
	if isinstance(rule, list):
		for r in rule:
			data = bili_filter_dict(name, data, r)
	else:
		data = bili_filter_dict(name, data, rule)
	flow.response.raw_content = bili_grpc_encode(data, template)

def response(flow) -> None:
	if flow.request.pretty_host == 'app.bilibili.com':
		# 推荐
		if flow.request.path.startswith('/x/v2/feed/index'):
			rule = {'data': {'items': [{'ad_info': is_none}, {'goto': is_allowed_goto}, {'title': is_allowed_text}, {'talk_back': is_allowed_text}, {'args': is_allowed_uploader}, {'owner': is_allowed_uploader}]}}
			bili_filter_json('/x/v2/feed/index', flow, rule)
		# 搜索 - 广场
		if flow.request.path.startswith('/x/v2/search/square?'):
			rule = {'data': {'data': {'list': [{'keyword': is_allowed_text}, {'show_name': is_allowed_text}]}}}
			bili_filter_json('/x/v2/search/square?', flow, rule)
		# 搜索 - 直播
		if flow.request.path.startswith('/x/v2/search/live?'):
			rule = {'data': {'live_room': {'items': [{'name': is_allowed_user}, {'title': is_allowed_text}, {'area_v2_name': is_allowed_text}, {'tags': is_allowed_text}]}}}
			bili_filter_json('/x/v2/search/live?', flow, rule)
		# 搜索 - 番剧/用户/影视/专栏
		if flow.request.path.startswith('/x/v2/search/type?'):
			# 用户
			r1 = {'data': {'items': [{'mid': is_allowed_uid}, {'title': is_allowed_text}, {'sign': is_allowed_text}]}}
			# 专栏
			r2 = {'data': {'items': [{'name': is_allowed_user}, {'title': is_allowed_text}, {'desc': is_allowed_text}]}}
			bili_filter_json('/x/v2/search/type?', flow, [r1, r2])
		# 搜索
		if flow.request.path.startswith('/x/v2/search?'):
			rule = {'data': {'item': [{'author': is_allowed_user}, {'title': is_allowed_text}, {'items': is_allowed_search_channel}]}}
			bili_filter_json('/x/v2/search?', flow, rule)
		# 主页
		if flow.request.path.startswith('/x/v2/space?'):
			rule = {'data': {'archive': {'item': [{'author': is_allowed_user}, {'title': is_allowed_text}]}}}
			bili_filter_json('/x/v2/space?', flow, rule)
	if flow.request.pretty_host == 'grpc.biliapi.net':
		# 相关视频
		if flow.request.path == '/bilibili.app.view.v1.View/View':
			rule = {'10': [{'3': is_allowed_text}, {'4': is_allowed_uploader}], '5':[{'2': is_allowed_text}]}
			bili_filter_grpc('/bilibili.app.view.v1.View/View', flow, rule)
		# 搜索提示
		if flow.request.path == '/bilibili.app.interface.v1.Search/Suggest3':
			rule = {'2': [{'2': is_allowed_text}, {'3': is_allowed_text}]}
			bili_filter_grpc('/bilibili.app.interface.v1.Search/Suggest3', flow, rule)
