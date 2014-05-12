import re
import threading
import socket
import select
import sys
import random
import time


size = 1024
sstrikefile = open('server_strikes','a')

#Client class
#Contains information about clients the server is working with.
class Client(object):
	#constructor
	def __init__(self, socket, name):
		self.socket = socket
		self.name = name
		self.strikes = 0
		self.status = "" #status : a = current turn, p = passed, w = skipped, 
				 #d = disconnected [to be disconnected], e = empty
		self.hand = []
		self.rank = 0 #The order the client finished their hand. Higher numbers mean they went out earlier
		self.outputBuffer = []
		self.inputBuffer = ""
		
	#Adds a strike to the client. If the client strikes out, changes their status
	def addStrike(self):
		sstrikefile.write("Struck %s" %self.name)
		self.strikes += 1
		if self.strikes >= 3:
		    self.status = "d"
	
	#Sends a message (contained in 'message') to the client
	def send(self,message):
		self.socket.send(message)
	
	#Returns if the client is still active
	#! Might be more efficient to just check the status, but this looks cleaner when reading for now
	def active(self):
		return self.strikes < 3
	
	#The client object sets itself up to be dropped
	def drop(self):
		self.strikes = 3
		self.status = "d"

#strike
#For a given client object, add one strike and send a strike message with the strikeCode number

def strike(client,strikeCode):
	if client.strikes < 3:
		client.addStrike()
		message = "[strik|%d|%d]" %(strikeCode,client.strikes)
		client.outputBuffer.append(message)
		if strikeCode / 10 in [1,7]:
			chand(client)

#cjoin
#Responds to a received cjoin message. Tests to see if the included name
#in the cjoin is legal,striking if it isn't. If it's legal but not available,
#it will add on a number to the backend of the name to make it legal.

def cjoin(client,message,used_names):
	#regular expression to check name is legal
	test = re.compile("(\W)")
	assign_name = message
	nameEnd = len(test.sub("",message))
	if nameEnd > 7:
		nameEnd = 6
	if assign_name in used_names:
		modifier = 0
		while assign_name in used_names:
			if modifier < 10:
				assign_name = assign_name[0:nameEnd] + str(modifier) + " "*(7-nameEnd)
			else:
				assign_name = assign_name[0:nameEnd-1] + str(modifier) + " "*(6-nameEnd)
			modifier += 1
	while len(assign_name) < 8:
		assign_name += " "
	used_names.append(assign_name)
	client.name = assign_name

####### GAME LOGIC METHODS ########

#shuffleDeck
#Makes a new array of integers 0-51 and returns the shuffled array

def shuffleDeck():
	deck = []
	for x in xrange(52):
		deck.append(x)
	random.shuffle(deck)
	return deck

# deal
# Given a list of players, it deals out the list as evenly as it can.
# playerList should be an list of players with the president at pos 0 and the scumbag at pos numPlayers-1
# Returns a list of client objects with their hands filled in.
def deal(playerList,sr):
	numPlayers = len(playerList)
	for p in playerList:
		p.hand = []
	cardsDealt = 0
	deck = shuffleDeck()
	while cardsDealt < 52:
		playerList[cardsDealt%numPlayers].hand.append(deck.pop(0))
		cardsDealt += 1
#sort the hands
	has00 = None
	for p in playerList:
		p.hand = sorted(p.hand)
		p.status = "w"
		if 00 in p.hand:
			has00 = p
	if sr == 1:
		has00.status = "a"
		print "set 00 status"
	else:
		playerList[0].status = "a"
	return playerList


#chand
#Server response to chand client message.
#Sends the client's current hand as seen by the server to the client.

def chand(client):
#format list to be sent
	message = ""
	if client.status == "d":
		return None
	for x in client.hand:
		if x < 10:
			message += "0%d," %x
		else:
			message += "%d," %x		
	while len(message)<54:
		message += str(52)+","
	client.outputBuffer.append("[shand|%s]" %message[0:53])

#cplay
#The server's response to a cplay message
#If the client sending the message is the currently active player, it checkes
#that the play is legal and, if it is, checks if it warrents a skip.
#returns [[cards played], T/F if next player is to be skipped]
#i.e. returns the cards played in a list and a boolean if there's a skip

def cplay(client,playCards,prevPlay,firstTurn):
	if client.status != "a":
		strike(client,15) #out of turn play
		print client.status
		return []
	else:
		cards = playCards.split(",")
		card_value = int(cards[0])/4
		skip = False
		if card_value != 13:
			prev_q = 0
			quantity = 0
			prev_v = 13
			for c in prevPlay:
				val = int(c)
				if val < 52:
					if val < 48:
						prev_q += 1
					if prev_v == 13:
						prev_v = val/4
			if prev_v < 12 and prev_v > card_value:
				strike(client,12) #value of cards is too low
				return []
			if firstTurn and "00" not in cards:
				strike(client,16) #tried to play first turn but doesn't have 00
				return []
			if prev_v == card_value:
				skip = True
			for c in cards:
				val = int(c)
				if val != 52:
					if val/4 != card_value :
						#print "%d != %d" %(val/4,card_value)
						strike(client,11) #cards don't have matching values
						return[]
					if val not in client.hand:
						strike(client,14) #card isn't in client's hand
						return[]
					quantity +=1
			if prev_q > quantity and card_value != 12:
				strike(client,13) # too few cards
				return []
			for c in cards:
				if c != "52": #pass/empty card
					client.hand.remove(int(c))
			client.status = "w"
		elif firstTurn:
			strike(client,18)
			return []
		else:
			client.status = "p"
		return [cards,skip]

# slobb
# Server sends out a message to all clients at the table and in the lobby
# with the current player list in the lobby.
def slobb(lobby,table):
	num_clients = len(lobby)
	n_c = ""
	body = ""
	if num_clients == 0:
		n_c = "00"
	else:
		body = "|"
		for c in xrange(num_clients):
			body += "%s," %lobby[c].name
		body =	body[0:len(body)-1]
		if num_clients < 10:
			n_c = "0" + str(num_clients)
		else:
			n_c = str(num_clients)
	for l in lobby:
		if l.active():
			l.outputBuffer.append("[slobb|%s%s]" %(n_c, body))
	for t in table:
		if t.active():
			t.outputBuffer.append("[slobb|%s%s]" %(n_c, body))
	return body


# stabl
# Sends out the current state of the table to all players at the table and in the lobby.
# Message formatted as: [stable|playerInfo|lastPlay|startingRound?]
# playerInfo = StatusStrikes:playerName:handSize	e.g. w2:Tyler   :10
# lastPlay = ##,##,##,##
# startingRound = 0 or 1, depending on whether or not it is the starting round [no rankings]
def stabl(lobby,table,lastPlay,sr):
	m1 = ""
	m2 = ""
	for t in table:
		hand = len(t.hand)
		two_dig = str(hand)
		if hand < 10:
			two_dig = "0" + two_dig
		#print t.status
		m1 += "%s%d:%s:%s," %(t.status,t.strikes,t.name,two_dig)
	while len(m1)<104:
		m1 += "e0:        :00,"
	m2 = "%s,%s,%s,%s" %(lastPlay[0],lastPlay[1],lastPlay[2],lastPlay[3])
	for l in lobby:
		if l.active():
			l.outputBuffer.append("[stabl|%s|%s|%d]" %(m1[0:104],m2,sr))
	for t in table:
		if t.active():
			t.outputBuffer.append("[stabl|%s|%s|%d]" %(m1[0:104],m2,sr))

# cchat
# Server response to cchat message.
# Checks if the length is 62 characters or less and sends out client's message to the table and the lobby

def cchat(client,message,lobby,table):
	if len(message) > 63:
		strike(client,32)
	while len(message) < 63:
		message = message + " "
	for l in lobby:
		if l.active() : l.outputBuffer.append ("[schat|%s|%s]" %(client.name,message))
	for t in table:
		if t.active() : t.outputBuffer.append ("[schat|%s|%s]" %(client.name,message))


# nextPlayer
# A game logic method.
# Finds the player who will take the next turn given the number of players remaining
# and the state of disconnects and skips.
# Changes the table status's to reflect whose turn it is and any skips that were made.
# Returns the next play to beat.

def nextPlayer(table,index,lastPlay,prevPlay,skip):
	if len(table) <= 1:
		return [prevPlay]
	#finds next player with cards
	next_player = index
	pos = index + 1
	go = True
	while go and pos != index: #POTENTIAL ERROR: Assumes there is at least one player with cards in their hand
		if pos >= len(table):
			pos = 0	
		if table[pos].active():
			go = len(table[pos].hand) == 0
		if not go :
			if skip:
				go = True
				skip = False
				table[pos].status = "p"
				pos += 1
			else:
				next_player = pos
		else:
			pos += 1
	if pos == index: #current player is the only one left with cards or the other player was skipped
		table[index].status = "a"
		return prevPlay
	if prevPlay == ["52"]*4: #player passed
		table[next_player].status = "a"
		pos = index #we don't need to check the current player: we know they passed
		while pos != next_player: #goes backwards through the table to see if everyone has passed:
			pos -= 1
			if pos < 0:
				pos += len(table)
			if table[pos].status == "w" and len(table[pos].hand) > 0: #player waiting with cards in their hand
				break
		if pos == next_player: #everyone passed
			return ["52"]*4
		else:
			return lastPlay
	else: #player played cards
		if prevPlay[0] in ["48","49","50","51"] and len(table[index].hand) > 0: #played a 2 and it's not their last card
			table[index].status = "a"
			return prevPlay
		else: #the 2 was the player's last card or a non-2 card was played
			table[next_player].status = "a"				
			return prevPlay

# startNewHand
# Game logic method
# Fills the table with up to 7 players from the lobby.
# If it's not the starting round, sorts the table according to rank (higher is better).
# Returns the new table, with hands fully dealt.

def startNewHand(lobby,table,minPlayer,sr):

	tsize = len(table)
	lsize = len(lobby)
	if tsize + lsize >= minPlayer:
		print "We're playing!"
		while tsize < 7 and lsize > 0:
			table.append(lobby.pop(0))
			tsize += 1
			lsize -=1
		organizedTable = []
		if sr == 0:
			#organize players by rank
			prank = 7 #playerRank
			while prank >= -1:
				for t in table:
					if t.rank == prank: 
						organizedTable.append(table[table.index(t)])
				prank -= 1;
		else:
			organizedTable = table
		return deal(organizedTable,sr)
	else: #not enough players to continue. Return players to lobby and reset sr
		return []


# validMessage
# A regular expression checker for message received from clients.
# If the message is invalid, it sends a strike.
# Returns a regular expression group. If None, the message is invalid

def validMessage(message,client):
	#use regular expression to check if message is in proper format
	#for cjoin, if illegal name just edit out illegal characters
	mType = message[1:6]
	check = None
	if mType == "cjoin":
		template = re.compile("\[(cjoin)\|([\w\W]*)\]")
		check = template.match(message)
	elif mType == "cchat":
		template = re.compile("\[(cchat)\|([^\[\]\:]*?)\]")
		check = template.match(message)
	elif mType == "cplay":
		template = re.compile("\[(cplay)\|(\d\d,\d\d,\d\d,\d\d)\]")
		check = template.match(message)
	elif mType == "cswap":
		template = re.compile("\[(cswap)\|(\d\d)]")
		check = template.match(message)
	elif mType == "chand":
		template = re.compile("\[(chand)\]")
		check = template.match(message)
	elif mType == "cquit":	
		template = re.compile("\[(cquit)\]")
		check = template.match(message)
	return check 



# splitMessages
# Given a string, it will split the string into separate messages.
# If a message was incomplete, stores it for later in the client's inputBuffer.
# Returns a list of strings, each containing a full message

def splitMessages(client):
	inMess = client.inputBuffer
	client.inputBuffer = ""
	newLines = re.compile("[\t\n\r\f\v]")
	inMess = newLines.sub("", inMess) #eliminates all whitespace characters except space
	numStart = inMess.count("[")
	numEnd = inMess.count("]")
	messStart = 0
	messEnd = len(inMess)
	full_messages = []
	while inMess != "":
		if numStart > 0: #the number of "[" > 0
			messStart = inMess.index("[")
			numStart -= 1
			if numEnd > 0: #there's an end bracket for the message
				messEnd = inMess.index("]")+1
				numEnd -= 1
				full_messages.append(inMess[messStart:messEnd])
				inMess = inMess[messEnd:len(inMess)]
			else: #incomplete message, store for later
				client.inputBuffer += inMess[0:len(inMess)]
				break
		else:
			print "Missed a start bracket"
			inMess = ""
			strike(client,30)
	if len(client.inputBuffer) > 1024: #prevents incomplete messages from clogging the inputBuffer for too long
		client.inputBuffer = ""
		client.outputBuffer = "[schat|  server|Your buffer has been flushed of incomplete messages"
		client.outputBuffer += " "*12 + "]"
	return full_messages	

# handleArg
# Handles commandline arguments, converting them to integers.

def handleArg(argType):
        return{
        '-t':1,
        '-m':2,
        '-l':3,
        }.get(argType,0)

# The main loop.
# Builds the server and runs it.

def main():
	#sets up host socket
	host = ''
	port = 36706
	backlog = 5
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
	s.bind((host,port))
	s.listen(backlog)
	
	#set up socket, lobby, and table variables
	read = [s,sys.stdin] #stores a list of sockets to read from (and from the keyboard)
	lobby = [] #stores clients who are in the lobby
	table = [] #stores clients who are currently playing at the table or who have struck out but the game hasn't ended
	names = [] #stores a collection of names that have been already used
	write = [] #stores a list of sockets to read from
	toDrop = [] #used for clients who strike out while in game

	#Sets up timer-related variables
	game = [False]
	pTimeout = [False]
	swapMade = [True]
	startTimer = [None]
	playTimer = None
	playTime = 30 #time player has to make play before getting a timeout	
	def playTimeout():
		pTimeout[0] = True
		swapMade[0] = True
	def gameStart():
		game[0] = True
		startTimer[0] = None
		print "timer works"

	#Game logic variables
	newHand = True #determines if it's time to deal a new hand
	gameTime = 15 #time between lobby filling up and the game starting
	finishRank = 0 #will contain num_players once game starts
	sr = 1 #1 if this is the starting round, 0 if it's not
	lastPlay = [52,52,52,52] #contains the value of the last non-pass play
	firstTurn = True #determines if it's the first round of a hand
	loop = True
	flag = 0
	minPlayer = 3

	#command line arguments
	for arg in sys.argv:
		if flag == 0:
			flag = handleArg(arg)
		elif flag == 1: #-t
			playTime = int(arg)
			flag = 0
		elif flag == 2:#-m
			minPlayer = int(arg)
			flag = 0
		elif flag == 3:#-l
			gameTime = int(arg)
			flag = 0

	# Processing loop
	while loop:
	    try:
		readList, writeList, emptyList = select.select(read,write,[])

##############################################################################################
################################ Start a new hand ############################################
##############################################################################################

		if game[0]:
			if newHand:
				game[0] = False
				if playTimer != None:
					playTimer.cancel()
				lastPlay = [52,52,52,52]
#				print "To drop: %s" %toDrop
				while toDrop:
					t = toDrop[0]
					#Makes sure t's socket is removed from read/write
					try:
					    read.remove(t.socket)
					except:
					    None
					try:
					    write.remove(t.socket)
					except:
					    None
					try:
					    t.socket.close()
					except:
					    None

					try:
					    names.remove(t.name)
					except ValueError:
					    print "Name %s not found to remove" %t.name
					t.outputBuffer = []
					table.remove(t)
					toDrop.remove(t)
					print "Dropped %s" %t.name

				oTable = startNewHand(lobby,table,minPlayer,sr)
				if oTable != []:
					print "\n\n\nNew hand \n\n\n"
					finishRank = len(table)
					slobb(lobby,table)
					table = oTable
					newHand = False
					if sr == 0:
						scumbag = table[len(table)-1]
						for t in table:
							if t != scumbag:
								chand(t)
						scumSwap = max(table[len(table)-1].hand)
						if scumSwap < 10:
							scumSwap = "0%d" %scumSwap
						else:
							scumSwap = str(scumSwap)
						table[0].outputBuffer.append("[swapw|%s]" %scumSwap)
						swapMade[0] = False
					else:
						for t in table:
							chand(t)
							t.rank = -1
						firstTurn = True
						stabl(lobby,table,lastPlay,sr)
					playTimer = threading.Timer(playTime,playTimeout)
					playTimer.start()
				else:
					sr = 1
					for x in xrange(len(table)):
						oldPlayer = table.pop(0)
						oldPlayer.rank = 0
						oldPlayer.status = "w"
						lobby.append(oldPlayer)
					game[0] = False

		# Or starts a new countdown timer
		elif len(lobby) >= minPlayer and startTimer[0] == None:
			startTimer[0] = threading.Timer(gameTime,gameStart)
			startTimer[0].start()

##############################################################################################
########################## Read messages from clients ########################################
##############################################################################################

#Read loop
		for r in readList:
			
#read from commandline
			if not loop:
			    break
			if (r == sys.stdin) :
				data = sys.stdin.readline()	
				if data == "close\n":
					for c in lobby:
						c.outputBuffer.append("[strik|00|3]")
						print "%s: %s" %(c.name,c.outputBuffer)
						c.status = "d"
					for c in table:
						c.outputBuffer.append("[strik|00|3]")
						print "%s : Buffer of %s" %(c.outputBuffer,c.name)
						c.status = "d"
					if startTimer[0] != None:
						startTimer[0].cancel()
					if playTimer != None:
						playTimer.cancel()
					loop = False
				elif data == "deal\n":
					deal(lobby,sr)
					stabl(lobby,lobby,lastPlay,sr)
				elif data == "lobby\n":
					print lobby
					for l in lobby:
						print l.name
				elif data == "table\n":
					print table
					for t in table:
						print "Player: %s. Status: %s" %(t.name,t.status)
				elif data == "names\n":
					print names
				elif data == "rank\n":
					print finishRank
				elif data == "data\n":
					print "Lobby:"
					for l in lobby:
						print l.name
					print "Table:"
					for t in table:
						print "Player: %s. Status: %s. Socket: %s. Active? %s" %(t.name,t.status,t.socket,t.active())
					print "Names:"
					for n in names:
						print n
					print "Write list:"
					for x in writeList:
						print x
					print "Read list:"
					for r in readList:
						print r
	
#add new clients
			elif (r == s) and loop:
				joinClient, address = s.accept()
				write.append(joinClient)
				if len(table) + len(lobby) <= 35: 
					read.append(joinClient)
					newClient = Client(joinClient,"")
					lobby.append(newClient)
					#print "read from s"
				else:
					strike(client,81)

#reads from clients in the lobby or the table
			elif loop:
				client = None
				if len(table) > 0:
					for t in table:
						if r == t.socket:
							client = t
				if client == None:	
					for l in lobby:
						if r == l.socket:
							client = l
							#print "Found client"
#read from clients
				data = ""
				try:
					data = r.recv(size)
				except socket.error:
					client.outputBuffer.append("[strik|00|3]")
					client.drop()
				if (client.strikes < 3): 
				    if len(data) == 0:
					    strike(client,33)
				    else:
					    client.inputBuffer += data
#					    print "received %s" %data
					    data = splitMessages(client)
					    for message in data:
						    if client.strikes >= 3:
							break
#						    print message
						    mParts = validMessage(message,client)
						    #print mParts.group(0)
						    if mParts is not None:
							    mType = mParts.group(1)
							    if mType == "cjoin":
								    if client.name == "":
									    cjoin(client,mParts.group(2)[0:8],names)
									    print "%s joined!" %client.name
									    client.outputBuffer.append("[sjoin|%s]" %client.name)
									    slobb(lobby,table)
								    else:
									    strike(client,30)
							    elif mType == "cquit":
								    client.drop()
								    client.outputBuffer.append("[strik|00|3]")
							    elif mType == "cchat":
								    #print "message = %s" %mParts.group(2)
								    cchat(client,mParts.group(2),lobby,table)
							    elif mType == "cplay":
								    play = []
								    if swapMade[0] and client in table:
									    if playTimer != None:
										    playTimer.cancel()
									    play = cplay(client,mParts.group(2),lastPlay,firstTurn)
									    if play != []:
										    if firstTurn:
											    firstTurn = False
										    if len(client.hand)==0:
											    client.rank = finishRank
											    finishRank -= 1
										    #contains a list with [position of next player, play to beat]
										    lastPlay = nextPlayer(table,table.index(client),lastPlay,play[0],play[1])
										    if finishRank > 1: 
											    stabl(lobby,table,lastPlay,sr)
										    else:
											    for t in table:
												    if t.status == "a":
													    t.status = "w"
											    stabl(lobby,table,lastPlay,sr)
											    newHand = True
											    sr = 0
									    if client.status == "d":
										    nextPlayer(table,table.index(client),lastPlay,["52"]*4,False)
										    if firstTurn:
											    firstTurn = False
									    playTimer = threading.Timer(playTime, playTimeout)
									    playTimer.start()
								    elif client in lobby:
									    strike(client,31)
								    else: #waiting for cswap
									    strike(client,70)
							    elif mType == "chand":
								    chand(client)
							    elif mType == "cswap":
								    #print "I got the swap"
								    scumCard = max(scumbag.hand)
								    #Someone who isn't the warlord is trying to pass
								    if client != table[0]:
									    strike(client,71)
								    #Passed back same card as scumbag passed
								    elif int(mParts.group(2)) == scumCard:
									    swapMade[0] = True
									    chand(scumbag)
									    stabl(lobby,table,["52"]*4,sr)
								    #Tried to pass a card they don't have
								    elif int(mParts.group(2)) not in client.hand:
									    #print "tried to pass card they didn't have"
									    strike(client,70)
								    #Make the pass
								    else:
									    #print "Gets stuck in the swapping"
									    scumbag = table[len(table)-1]
									    warCard = int(mParts.group(2))
									    #moves card from warlord to scumbag and re-sorts
									    client.hand.remove(warCard)
									    client.hand.append(scumCard)
									    client.hand = sorted(client.hand)
									    #gives card to scumbag and removes highcard
									    scumbag.hand.append(warCard)
									    scumbag.hand.remove(scumCard)
									    scumbag.hand = sorted(scumbag.hand)
									    scumMess = ("[swaps|%s|" %(mParts.group(2)))
									    if scumCard < 10:
										    scumMess += "0%d]" %scumCard
									    else:
										    scumMess += str(scumCard) + "]"
									    if scumbag.active(): 
										    scumbag.outputBuffer.append(scumMess)
									    chand(scumbag)
									    swapMade = [True]
									    stabl(lobby,table,lastPlay,sr)
							    else :
								    strike(client,33)    
						    else:
							    strike(client,33)
							    
##############################################################################################
############################ Send messages to clients ########################################
##############################################################################################

# Send messages to all lobby clients
		for l in lobby:
			if len(l.outputBuffer) > 0:
				for w in writeList:
					if w == l.socket:
						try:
							bytesSent = 0
							while l.outputBuffer != []:
								outMess = l.outputBuffer[0]
								bytesSent += len(outMess)
								if bytesSent < 1024:
									l.socket.send(outMess)
									l.outputBuffer.pop(0)
#									print outMess
								else:
									break
							#print l.name
							if l.strikes > 2:
								raise socket.error
							break
						except socket.error:
							l.status = "d"
							l.outputBuffer = []
							
#drops people from the lobby if they need to be dropped
		inLobby = len(lobby)
		x = 0
		deleted = False
		while x < inLobby:
			l = lobby[x]
			if not l.active():
				deleted = True
				read.remove(l.socket)
				lobby.remove(l)
				names.remove(l.name)
				write.remove(l.socket)
				l.socket.close()
				print "dropped %s" %l.name
				inLobby -= 1
			else:
				x += 1
		if deleted:
			slobb(lobby,table)
			
# Write loop for all clients at the table
		for t in table:
			if len(t.outputBuffer) > 0:
#				print "%s %s %s" %(t.name, t.status, t.outputBuffer)
				for w in writeList:
					if w == t.socket:
						try:
							bytesSent = 0
							while t.outputBuffer != []:
								outMess = t.outputBuffer[0]
								bytesSent += len(outMess)
								if bytesSent < 1024:
									t.socket.send(outMess)
									t.outputBuffer.pop(0)
#									print outMess
								else:
									break
							if t.strikes > 2:
								raise socket.error
						except:
							t.drop()
							t.outputBuffer = []
							finishRank -= 1
							if firstTurn:
								firstTurn = False
							if not swapMade[0]:
								swapMade[0] = True
							#contains a list with [position of next player, play to beat]
							t.outputBuffer = []
							if finishRank > 1:
							    if t.status == "a": 
								t.status = "d"
								lastPlay = nextPlayer(table,table.index(t),lastPlay,["52"]*4,False)
								stabl(lobby,table,lastPlay,sr)
							else: #dropping player left only one player with cards in their hand
								print "Not enough to continue play"
								t.status = "d"
								for t in table:
									if t.status == "a":
										t.status = "w"
								newHand = True
								sr = 0

#disconnects sockets from table, appends them to be dropped
		inTable = len(table)
		x = 0
		while x < inTable:
			t = table[x]
			if not t.active() and t not in toDrop:
			        deleted = True
				toDrop.append(t)
				read.remove(t.socket)
				write.remove(t.socket)
				t.socket.close()
				inTable -= 1
			else:
				x += 1

##############################################################################################
############################### Player timeouts ##############################################
##############################################################################################

		if pTimeout[0]:
			#find player
			#call nextPlayer(table,player,lastPlay,False)
			#restart timer
			for t in table:
				if t.status == "a":
					if swapMade[0] == False:
						swapMade[0] = True
						pTimeout[0] = False
						chand(table[len(table)-1])
					strike(t,20)
					if t.status == "d":
						nextPlayer(table,table.index(t),lastPlay,["52"]*4,False)
						firstTurn = False
						pTimeout[0] = False # a flag to show that the player has timed out and struck out
					break
			#Player struck out
			if not pTimeout[0]:
				if stabl(lobby,table,lastPlay,sr) <= 1:
					sr = 1
					newHand = True
			pTimeout[0] = False
			playTimer =  threading.Timer(playTime, playTimeout)
			playTimer.start()
#starts a game timer if a hand is over
		if newHand and sr == 0 and startTimer[0] == None:
			startTimer[0] = threading.Timer(2,gameStart)
			startTimer[0].start()
	    except socket.error:
		print "Socket crashed where it shouldn't have. Whoops"
	s.close()

######################################################################################################

#starts the program
main()
