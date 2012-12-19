# -*- coding: utf-8 -*-
from asyncore import dispatcher
from asynchat import async_chat
import socket
import asyncore
import time
import cPickle

PORT = 50000
NAME = "CodeCafe"

UserLst = []
usrDB = open("userdata", "rb")
while 1:
	try:
		UserLst.append(cPickle.load(usrDB))
	except EOFError:
		break
usrDB.close()
UserDict = dict([(u["username"], u) for u in UserLst])

def writeUserData(userlst):
	ouf = open("userdata", "wb")
	for user in userlst:
		cPickle.dump(user, ouf, 2)
	ouf.close()

class EndSession(Exception):
	pass

class CommandHandler(object):
	"""docstring for CommandHandler"""
	def unknown(self, session, cmd):
		session.push("Unknown command: %s\r\n" % cmd)

	def handle(self, session, line):
		if not line.strip():
			return
		parts = line.split(' ', 1)
		cmd = parts[0]
		try:
			line = parts[1].strip()
		except IndexError:
			line = ''
		method = getattr(self, 'do_'+cmd, None)
		try:
			method(session, line)
		except TypeError:
			self.unknown(session, cmd)

class Room(CommandHandler):

	def __init__(self, server):
		self.server = server
		self.sessions = []

	def add(self, session):
		self.sessions.append(session)

	def remove(self, session):
		self.sessions.remove(session)

	def broadcast(self, line):
		for session in self.sessions:
			session.push(line)

	def do_logout(self, session, line):
		raise EndSession

class LoginRoom(Room):

	def add(self, session):
		Room.add(self, session)
		self.broadcast("Welcome to %s\r\n" % self.server.name)

	def unknown(self, session, cmd):
		session.push("Please log in\nUse 'login <nick>'\r\n")

	def do_login(self, session, line):
		name, pwd = line.strip().split(' ')
		if name in UserDict and UserDict[name]["password"] == pwd:
			if not name in self.server.users:
				session.user = UserDict[name]
				session.push("Welcome, %s\r\n" % name)
				session.push("account %s \r\n" % cPickle.dumps(session.user, 2))
				session.enter(self.server.main_room)
			else:
				session.push("The user %s is already online!\r\n" % name)
		else:
			session.push("unknown user name or bad password.\r\n")

class ChatRoom(Room):

	def add(self, session):
		self.broadcast(session.user["username"]+ " has enter the room.\r\n")
		self.server.users[session.user["username"]] = session
		Room.add(self, session)

	def remove(self, session):
		Room.remove(self, session)
		self.broadcast(session.user["username"] + " has left the room.\r\n")

	def do_say(self, session, line):
		dst, msg = line.split(' ', 1)
		nowtime = time.strftime('%H:%M:%S')
		msgPkg = nowtime + ' ' + session.user["username"] + " to " + dst + ": \n" + msg + "\r\n"
		if dst == "-all":
			self.broadcast(msgPkg)
		else:
			dstSession = self.server.users.get(dst)
			if dstSession:
				dstSession.push(msgPkg)
				session.push(msgPkg)
			else:
				session.push("No such person online.\r\n")

	def do_editBoard(self, session, line):
		if session.user["isAdmin"]:
			self.server.board = line
			self.broadcast("board " + line + "\r\n")
			self.server.writeBoards()
		else:
			session.push("error You don't have permission.\r\n")

	def do_editAppointment(self, session, line):
		index, content = line.split(' ', 1)
		if session.user["isAdmin"]:
			self.server.appointments[int(index)] = content
			self.broadcast("appointment " + line + "\r\n")
			self.server.writeBoards()
		else:
			session.push("error You don't have permission.\r\n")

	def do_refresh(self, session, line):
		session.push("board " + self.server.board + "\r\n")
		for i, content in enumerate(self.server.appointments):
			session.push("appointment %d %s\r\n" % (i, content))
		session.push("user " + ' '.join(name for name in self.server.users) + "\r\n")

	def do_look(self, session, line):
		session.push("The following are in this room:\r\n")
		for other in self.sessions:
			session.push(other.user["username"] + "\r\n")

	def do_who(self, session, line):
		session.push("The following are logged in:\r\n")
		for name in self.server.users:
			session.push(name + "\r\n")

class LogoutRoom(Room):

	def add(self, session):
		try:
			del self.server.users[session.user["username"]]
		except KeyError:
			pass

class ChatSession(async_chat):

	def __init__(self, server, sock):
		async_chat.__init__(self, sock)
		self.server = server
		self.set_terminator("\r\n")
		self.data = []
		self.user = None
		self.enter(LoginRoom(server))

	def enter(self, room):
		try:
			cur = self.room
		except AttributeError:
			pass
		else:
			cur.remove(self)
		self.room = room
		room.add(self)

	def collect_incoming_data(self, data):
		self.data.append(data)

	def found_terminator(self):
		line = ''.join(self.data)
		self.data = []
		try:
			self.room.handle(self, line)
		except EndSession:
			self.handle_close()

	def handle_close(self):
		async_chat.handle_close(self)
		self.enter(LogoutRoom(self.server))

class MessageServer(dispatcher):

	def __init__(self, port, name):
		dispatcher.__init__(self)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind(('', port))
		self.listen(5)
		self.name = name
		inf = open('boards', 'rb')
		self.board = cPickle.load(inf)
		self.appointments = cPickle.load(inf)
		inf.close()
		self.users = {}
		self.main_room = ChatRoom(self)
		print "Successfully initialize MessageServer."

	def handle_accept(self):
		connetion, addr = self.accept()
		ChatSession(self, connetion)

	def writeBoards(self):
		ouf = open("boards", "wb")
		cPickle.dump(self.board, ouf, 2)
		cPickle.dump(self.appointments, ouf, 2)
		ouf.close()

if __name__ == '__main__':
	s = MessageServer(PORT, NAME)
	try:
		asyncore.loop()
	except KeyboardInterrupt:
		print