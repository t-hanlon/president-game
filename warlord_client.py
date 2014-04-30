import socket
import select
import sys
import re
import time

def validMessage(message):
	mType = message[1:6]
	check = None
	if mType == "sjoin":
		template = re.compile("\[(sjoin)\|([\w ]*)|[^\]\[]{8,8}\]")
		check = template.match(message)
	elif mType == "schat":
		template = re.compile("\[(schat)\|([^\[\]\:]{8,8})\|([^\]\[]{0,63})\]")
		check = template.match(message)
	elif mType == "slobb":	
		template = re.compile("\[(slobb)\|(\d\d)(\|(([\w ]{8,8})(,[\w ]{8,8})*)){0,1}\]")
		check = template.match(message)
	elif mType == "stabl":
		template = re.compile("\[(stabl)\|(([adwpeADWPE]\d:[\w ]{8,8}:\d\d,){6,6}[adwpe]\d:[\w ]{8,8}:\d\d)\|(\d\d,\d\d,\d\d,\d\d)\|\d\]")
		check = template.match(message)
	elif mType == "swaps":
		template = re.compile("\[(swaps)\|(\d\d)\|(\d\d)\]")
		check = template.match(message)
	elif mType == "swapw":
		template = re.compile("\[(swapw)\|(\d\d)\]")
		check = template.match(message)
	elif mType == "shand": #creates a group with most of the cards and the final card is in its own group
		template = re.compile("\[(shand)\|((\d\d,){0,17}\d\d)\]")
		check = template.match(message)
	elif mType == "strik":
		template = re.compile("\[(strik)\|(\d\d)\|(\d)\]")
		check = template.match(message)
	else:
		print "Received invalid message: %s. Put in buffer to wait for complete message." %(message)
	return check


#splits messages into their parts
def splitMessages(inMess):
        numStart = inMess.count("[")
        numEnd = inMess.count("]")
	newLines = re.compile("[\t\n\r\f\v]")
	inMess = newLines.sub("",inMess)
        messStart = 0
        messEnd = len(inMess)
        full_messages = []
        comp_message = ""
        while inMess != "":
                if numStart > 0:
                        messStart = inMess.index("[")
                        numStart -= 1
                else:
                        print "incomplete message alert"
                if numEnd > 0:
                        messEnd = inMess.index("]")+1
                        numEnd -= 1
                else:
                        print "incomplete message alert"
                full_messages.append(inMess[messStart:messEnd])
                inMess = inMess[messEnd:len(inMess)]
        return full_messages



#TODO rewrite chand to write hand into variable hand as ints
def autoplay(hand,lastPlay):
	beat_value = int(lastPlay[0])/4
	print beat_value
	if beat_value >= 12:
		beat_value = 0
		beat_quant = 0
	else:
		beat_quant = 4 - lastPlay.count("52")
	play = []
	#find the lowest and the most cards it can
	dif_values = len(hand)
	for x in xrange(dif_values):
		c = hand[x]
		if c[0] >= beat_value:
			if c[1] >= beat_quant:
				play = hand.pop(x)
		if play != []:
			break
	#converts the formatted play into a message
	#print play
	if play == [] :
		playMsg = "52,52,52,52"
	else:
		playMsg = "" 
		for card in play[2]:
			if card < 10:
				playMsg += "0%d," %card
			else:
				playMsg += str(card) + ","
	return [playMsg[0:11],hand]
		
#creates a hand in valid play format in the form [value, quantity, [card card card card]]
def makeHand(hand):
	newHand = []
	likeCards = []
	prevC = -1
	for c in hand:
		card = int(c)
		value = card/4
		if value == 13:
			break
		if value == 12:
			if prevC != 12:
				num_cards = len(likeCards)
				likeCards = likeCards + [52]*3 #pads with 52's [no cards]
				newHand.append([prevC,num_cards,likeCards[0:4]])
				prevC = 12
				likeCards = [card]
			else:
				newHand.append([12,1,likeCards+[52,52,52]])
				likeCards = [card]
		elif value != prevC:
			if prevC > -1: #as long as likeCards has something in it, add it to the hand
				num_cards = len(likeCards)
				likeCards = likeCards + [52]*3 #pads with 52's [no cards]
				newHand.append([prevC,num_cards,likeCards[0:4]])
			likeCards = [card]
			prevC = value
		else: #cards have same value
			likeCards.append(card)
	num_cards = len(likeCards)
	likeCards = likeCards + [52]*3
	newHand.append([prevC,num_cards,likeCards[0:4]])
	return newHand

def handleArg(argType):
	return{
	'-s':1,
	'-p':2,
	'-n':3,
	'-m':4,
	'-q':5
}.get(argType,0)

host = 'localhost'
port = 36706
backlog = 5
size = 1024
name = ""
auto = True
run = True
quit = False
flag = 0 #flags what type of argument has been input
for arg in sys.argv:	
	if not arg.startswith("-"):
		if flag == 1:
			host = arg
			flag = 0
		elif flag == 2:
			port = int(arg)
			flag = 0
		elif flag == 3:
			if name != "": name += " "
			name += arg
		#checks if arg was -m, which doesn't have an arg following it
	elif flag in [0,3]:
		flag = handleArg(arg)
		if flag == 4:
			auto = False
			flag = 0
		elif flag == 5:
			quit = True
			flag = 0
	else:
		print "Error in commandline arguments"
		run = False
#	print "%d %s -- %s %s %s" %(flag,arg,host,port,name)

#print name	
if name == "":
	name = raw_input("Pick desired name for server:")
while len(name) < 8:
	name = name + " "
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((host,port))
outputBuffer = "[cjoin|%s]" %name
name = ""
send = True
read = [s,sys.stdin]
write = [s]
if not quit:
	strikefile = open('errorfile','a')
modify = -1 #Means that this client swapped, thus needs to modify their hand
turn = False
hand = []	#list of lists. Each list contains all cards with a given value. Every 2 gets its own list
inBuffer = ""
print "Command:"
while run:
	inputList, outputList, emptyList = select.select(read,write,[])
	if modify >= 0:		#adds the received card
		added = False
		val = modify/4
		if val == 12:
			hand.append([12,1,[modify,52,52,52]])
			added = True
		else:
			for cards in hand:
				if cards[0] == val:
					cards[2][cards[1]] = modify
					cards[1] += 1
					added = True
		if not added:
			hand.append([val,1,[modify,52,52,52]])
		modify = -1
	for i in inputList:
		if (i == sys.stdin):
		    command = sys.stdin.readline()
		    command = command[0:(len(command)-1)] #removes the \n at the end
		    if command == "help":
			print "valid commands: \njoin name \nquit"
		    else :
			inMess = command.split(" ")
			send = True
			mType = inMess[0]
			if mType == "join":
			    while len(inMess[1]) < 8:
				inMess[1] = inMess[1] + " "
			    outputBuffer += "[cjoin|%s]" %inMess[1]
			elif mType == "quit":
				run = False
			elif mType == "chat" or mType == "c":
				print inMess
				if len(inMess) < 2:
					print "Error: chat requires a non-empty message"
					send = False
				else:					
					message = ""
					x = 1
					while x < len(inMess):
						message += inMess[x] + " "
						x += 1
					while len(message) < 63:
						message += " "
					outputBuffer += ("[cchat|%s]" %message)
			elif mType in ["play","p"]:
				while len(inMess) < 5:
					inMess.append("52")
				if len(inMess) == 5:
					outputBuffer += "[cplay|%s,%s,%s,%s]" %(inMess[1],inMess[2],inMess[3],inMess[4])
				else:
					print inMess
					send = False
			elif mType == "swap":
				outputBuffer += "[cswap|%s]" %inMess[1]
			elif mType == "show hand" or mType == "hand":
				print hand
				outputBuffer += "[chand]"
			elif mType == "name":
				print name
			else:
				print "invalid command"
		elif i == s:
#			print inBuffer
			inBuffer += i.recv(size)
			messages = splitMessages(inBuffer)
#			print messages
			inBuffer = ""
			if messages == []:
				run = False
			for data in messages:
#			    print "Debug original: %s" %data
			    mParts = validMessage(data)
			    if mParts != None:
				mType = mParts.group(1)
				print mType
				if mType == "strik":
					print "Received strike, error code %s \n Strike count: %s" %(mParts.group(2),mParts.group(3))
					if not quit:
						strikefile.write("%s -- Strike code: %s\n" %(name,mParts.group(2)))
						strikefile.flush()
					if int(mParts.group(3)) >= 3:
						s.close()					
						run = False
					if int(mParts.group(2))/10 == 1:
						print hand
				elif mType == "sjoin":
					print "Join success! Your name is " + mParts.group(2)[0:9]
					name = mParts.group(2)
					if quit:
						send = True
						outputBuffer += "[cquit]"
						time.sleep(.5)
				elif mType == "schat":
					print "%s:%s" %(mParts.group(2),mParts.group(3)[0:64])
				elif mType == "stabl":
					#interpret table
#					print mParts.group()
					playerList = mParts.group(2).split(",")
					lastPlay = mParts.group(4).split(",")
					playerInfo = []
					for player in playerList:
						playerInfo.append(player.split(":"))
					go = False #truth value for other players still participating in the game
					for player in playerInfo:
						print player
						if name == player[1]:
							turn = player[0].startswith("a")
						elif player[0].startswith(("a","w","p")) and player[2] != "00":
							go = True #hand != []
					if turn and modify < 0:
						if auto and go:
							print lastPlay
							play_hand = autoplay(hand,lastPlay)
							send = True
							#formats into sendable message
							outputBuffer += "[cplay|%s]" %play_hand[0]
							hand = play_hand[1]
						else:
							message = ""
							if go: 
								message = "It's your turn. "
							else:
								message = "Hand over. "
							print message + "The last play was: %s" %lastPlay
						
				elif mType == "slobb":
					print "%s players." %mParts.group(2)
					if mParts.group(3) != "00":
						print "Names: %s" %mParts.group(4)
				elif mType == "shand":
					print mParts.group()
					hand = makeHand(sorted(mParts.group(2).split(",")))
					print hand
				elif mType == "swapw": #request to swap card for warlord
					print "I'm supposed to swap"
					if auto:				
					#give lowest singleton
						notQuant = True
						passQuant = 0
						while notQuant:
							passQuant += 1
							for cards in hand:				#AI -- check value of card
								if cards[1] == passQuant:
									pas = cards[2][0]
									if pas < 10:
										pas = "0" + str(pas)
									else:	
										pas = str(pas)	
									outputBuffer += "[cswap|%s]" %pas
									send = True
									hand.pop(hand.index(cards))
									modify = int(mParts.group(2))
									notQuant = False
									print cards
									break
					else: 
						print "You're the warlord. The scumbag will give you %s. What card will you pass?" %(mParts.group(2))
				elif mType == "swaps":
					print "You're the scumbag. You would have gotten %s, but the warlord has gifted you %s" %(mParts.group(3),mParts.group(2))
			    else:
				inBuffer += data


	if send and run:
		for o in outputList:
			if o == s:
				o.send(outputBuffer)
				print "sent " + outputBuffer
				send = False
				outputBuffer = ""

