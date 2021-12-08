"""
Basic back-end server for the organizer project, built with the python Flask library.
Author:	Jamie Thorup
Date:	7/15/2021
"""

# Import dependencies
from inspect import FullArgSpec
from re import S, search
import re
from typing import Sequence
from flask import Flask, render_template, redirect, url_for, request, jsonify, make_response
from flaskext.mysql import MySQL
from flask_oidc import OpenIDConnect
from okta.client import Client as UsersClient
import csv
import sys
import json
import requests

# CSV data we use for the DB -- replace with WORKDAY data later
# CSV_DIR = './datacsv.csv' # <---- old, outdated data used for debugging
CSV_DIR = './under_david_walker.csv' # make sure `TOP_NODE` is set to "David_Walker" or whoever is at the very top of the tree --> used to make default tree

# DB constants
DB_TO_USE		= 'default'						# name of the DB itself
TABLE_TO_USE	= 'tbl_data'				# name of the hierarchy data table in the DB (comes from the .csv/Workday data)
CUST_DAT		= 'cust_data'				# name of the custom data table in the DB
RESULT_SIZE 	= 400						# limits amount of results returned in a query to this number
NODES_ON_SCREEN = 100						# limits the number of nodes on screen at a given time

# Other Constants
GROUP_MAX 		= 5							# limits the degrees of seaparation used in creating the visual tree
TOP_NODE 		= "David_Walker"			# Preset name of the top individual in the database -- the root node to all employees.
WP_INDEX = '/2D_front_end/splash.html'		# splash page seen by user when they visit `https://<URL>/`
WP_DASH = '/2D_front_end/index.html'		# page that actually has the organizer tool

# establish the Flask server itself
app = Flask(__name__, static_folder='static', static_url_path='/static')

# Configure OpenID Connect
app.config["OIDC_CLIENT_SECRETS"] = "client_secrets.json"
app.config["OIDC_COOKIE_SECURE"] = False		# remove this in order to use SSL
app.config["OIDC_CALLBACK_ROUTE"] = "/authorization-code/callback"
app.config["OIDC_SCOPES"] = ["openid", "email", "profile"]
app.config["SECRET_KEY"] = "Ky" 				# nonce-like; used to encrypt Flask sessions (cookies). This should be private
app.config["OIDC_ID_TOKEN_COOKIE_NAME"] = "oidc_token"
oidc = OpenIDConnect(app)
okta_client = None

# set up for MySQL Database connection
mysql = MySQL()
app.config['MYSQL_DATABASE_USER'] = 'root'
app.config['MYSQL_DATABASE_PASSWORD'] = 'wp'
app.config['MYSQL_DATABASE_DB'] = 'default'
app.config['MYSQL_DATABASE_HOST'] = 'mysql'		# for docker container, use `host.docker.internal`
mysql.init_app(app)

# establish connection with the MySQL DB
limit = 0
while limit < 3:
	try :
		conn = mysql.connect()
		break
	except:
		print("--------Error connecting server.py to mysql backend!--------")
		limit += 1
cursor = conn.cursor()

# remove everything from main table in the database upon startup
print('Truncating table...')
# s = f'USE {DB_TO_USE}'
# cursor.execute(s)
s = f'TRUNCATE TABLE {TABLE_TO_USE}'
cursor.execute(s)
conn.commit()		# commit the transaction with the DB

# set default search query values
search_q = None
result = None
column_number = 1			# number associated with column in `column_search`; indexed at zero
previously_searched = ""	# keeps track of the last search
previous_result	= ""		# keeps track of last result
email = ""					# the user's email given by Okta
name = None					# the user's name given by Okta
node = ""					# the node (name) clicked on by the user
isCustData = False			# global flag used to add custom data for a node (name)
node_num = 1				# used to track the number of nodes on screen
node_num_flag = False		# global flag used to render "too many nodes!" message
multi_list_src = None		# keeps track of the multiple search results (names) the user can choose from for a given search
render_back_bttn = False	# global flag that determines whether or not to render the on-screen back button

# set up the main data structure
# this struc becomes a JSON object that is sent to the front-end and used to render the 2D nodes
send_data = {'nodes':[],  'links': []}

# process the .csv data provided and put it into the DB --> note, this step needs to be replaced in the future with data taken from Workday!
print('Loading data into DB...')
with open(CSV_DIR, encoding="ISO-8859-1") as fp:
	reader = csv.reader(fp, delimiter=",", quotechar='"')
	for row in reader:
		# Converts each row to a formatted string, similar to the output of `print(row)`
		j = ', '.join('"{0}"'.format(w) for w in row)	

		# insert data into DB
		s = f'INSERT into {TABLE_TO_USE} values({j})'
		cursor.execute(s) 

# Remove the first row from the DB, since it contains the column headers
print('Deleting unneeded first row...')
cursor.execute(f'DELETE FROM `{TABLE_TO_USE}` LIMIT 1')
conn.commit()


########################################################################	Functions	########################################################################

"""
searchDB:		searches the DB for a term and returns the result from the DB. Dending on flags, returns a tuple or, if multiple
				results are found, a list of tuples from the DB. Returns cursor with DB search result by default.

----Variables----
search_term:	the input for the search
column:			the column in the DB to search 
table:			the table in the DB to search
fetchAll:		flags whether or not to fetch all results from DB
fetchOne:		flags whether or not to fetch one result from DB
"""
def searchDB(search_term, column, table, fetchAll=False, fetchOne=False):
	term = search_term.replace("\'", "\'\'")	
	s = f'SELECT * from {DB_TO_USE}.{table} where {column} like \'%{term}%\''
	cursor.execute(s)
	if fetchAll:
		return cursor.fetchall()
	elif fetchOne:
		return cursor.fetchone()
	return cursor

"""
checkForCustData:	Returns true if an entry for the selected node is found in the database. Returns false otherwise.
					Also set the global flag `isCustData` to match the main return. i.e. if there is an entry in the custom
					database, the function will both set `isCustData` to True and return True

----Variables----
node:				the node we want to check to see if it has an entry. String. Formatted <first name>_<last name>
"""
def checkForCustData(node):
	global isCustData
	node = node.replace("\'", "\'\'")
	s = f'SELECT * from {DB_TO_USE}.{CUST_DAT} where user like \'%{node}%\''
	cursor.execute(s)
	result = cursor.fetchone()
	if result:
		isCustData = True
		return True
	isCustData = False
	return False


"""
createTree:		Recursively searches the reportsTo column in order to add to the `send_data` data structure.
				The struc is formatted as a dictionary, which can be later translated to a JSON object in order 
				to be used by the front-end script. 

----Variables----
query:			a string representing the person we're searching for in that iteration.
group:			the degree of separation a node has from the root of the three
is_mult_list:	flag used to override the degrees of separation from a displayed node; used to display one layer of names from a search returning multiple results
"""
def createTree(query, group, is_mult_list=False):
	global send_data	# establish the data structure as a global variable
	global conn			# establish the mysql variables as global variables
	global cursor
	global node_num		
	global node_num_flag

	# base case: search for input `query`, and if it's null, return from the fuction w/ null
	for_search = query.replace("\'", "\'\'")		# modify the query so we can actually search or names containing approstrophes in the DB
	s = f'SELECT * from {DB_TO_USE}.{TABLE_TO_USE} where reportsTo like \'%{for_search}%\''
	cursor.execute(s)
	temp_list = cursor.fetchmany(size=RESULT_SIZE)
	# cursor.fetchall()		# fetch the rest of the rows in order to execute new statements
	
	if temp_list:		# if `temp_list` is not empty, i.e. there are children nodes beneath the current node
		# return None			# return without describing any new links

		# use the tuple returned by the search and iterate through each item
		for item in temp_list:

			# format the string to get just the name of the individual
			s0 = item[1].split()
			
			item_name = s0[0] + '_'+ s0[1] 
			item_name = item_name.replace("\'", "\'\'")

			# check to see if the individiual is listed as a node already.
			cont_node_flag = False
			if send_data['nodes']:					# if there are nodes in the list,
				for dict in send_data['nodes']:		# go through each node's dictionary
					if dict['id'] == item_name:		# and see if the person's name is there
						cont_node_flag = True	

			# if the node is not in the list, add it
			if not cont_node_flag:
				send_data['nodes'].append({"id": item_name, "group":group})
			
				# recursion step --> goes thru the rest of the child nodes and adds descriptions for the links between parent-child nodes
				if (group < GROUP_MAX and node_num < NODES_ON_SCREEN):
					node_num += 1
					# print("node num:\t", node_num)
					createTree(item_name, group + 1)
				else:
					node_num_flag = True
		
			# add the new link to `send_data['links']`
			temp_dict = {"source": item_name, "target": query, "value":(1 / group)}	# we may want to add the value argument here
			send_data['links'].append(temp_dict)
	
	return	# return from createTree


"""
addBoss:		Adds a boss to the tree.

----Variables----
full_term:		The full name of the person that the boss will be attached to in the tree
boss_name:		A formatted version of the boss' name: <first name>_<last name>
isSkill:		flags whether the function is being used for a skill (searches for name in a different index)		
"""
def addBoss(full_term, name, isSkill=False):
	if isSkill:
		reg_name = name
		boss_name = 'Reports To: ' + name
	else:
		temp = name.split("_")
		reg_name = temp[1] + '_' + temp[2]
		boss_name = 'Reports To: ' + temp[1] + "_" + temp[2]
	add_boss = True
	add_alt_link = False
	temp_dict = {}

	# check if the boss is already in the nodes list
	for dict in send_data['nodes']:
		if boss_name in dict.values():
			add_boss = False
		# check if the boss (as a person) is already in the tree
		if reg_name in dict.values():
			add_alt_link = True

	if add_boss:
		send_data['nodes'].append({"id": boss_name, "group":0})				# add the boss as a node to the list of nodes
	
	if add_alt_link:
		temp_dict = {"source": full_term, "target": reg_name, "value":1}
	else:
		temp_dict = {"source": full_term, "target": boss_name, "value":1}
	send_data['links'].append(temp_dict)									# add boss-query link to list of links

"""
addUser:	Creates a new tree to be rendered by the front-end. Adds the searched-for person (and their boss, if applicable)
				to the base of the tree and then recursively finds and adds all related people under the searched-for person.
				The tree render is limited by the global variable `GROUP-MAX`, which limits the degrees of separation from the 
				searched-for person that is displayed by the tree. 

----Variables----
result:			the search result of the query from the database
full_term:		the search query (a person's name) that spit out `result` from the database. Formatted <first name>_<last name>
is_mult_list:	flag used to override the degrees of separation from a displayed node; used to display one layer of names from a search returning multiple results
"""
def addUser(result, full_term, is_mult_list=False):
	global node_num
	global node_num_flag
	group = 0
	node_num = 1
	node_num_flag = False

	# get the boss' name if possible
	if result[2] != None:
		boss_lowercase = result[2].lower()
	
	if (boss_lowercase.islower()):		# check that the name has valid characters
		addBoss(full_term, result[2])	# Add boss to the tree
		group += 1
	
	send_data['nodes'].append({"id": full_term, "group":group})		# add the name as a node to the list of nodes
	group += 1
	createTree(full_term, group, is_mult_list=is_mult_list)			# do recursion to gather all of the nodes and links

"""
peopleOnNode():	creates a node with multiple individuals from the DB attached to it.

----Variables----
result:			the list of people to be attached to the base node. A list of tuples from the DB
base_node:		name of the base node all the names will be attached to.
isSkill:		flags whether `base_node` is a skill, i.e. not a person (searches for name in a different index)

"""
def peopleOnNode(result, base_node, isSkill=False):
	boss_name = ""

	# add base_node to tree
	send_data['nodes'].append({"id": base_node, "group":0})
	
	# add each person to the tree
	for item in result:
		
		# get the person's name and boss' names
		if isSkill:		# if the base node is not a person's name
			# grab person's name
			full_term = item[0]	

			# find person's entry in the hierarchy (.csv file)
			s = f'SELECT * from {DB_TO_USE}.{TABLE_TO_USE} where userName like \'%{full_term}%\''
			cursor.execute(s)
			result = cursor.fetchone()
			
			# check if we got a result & get boss' name accordingly
			if result:
				boss_name = result[2]	# get boss' name	
			else:
				boss_name = "No_Boss_Found"

		else:
			# create person's and boss' names
			temp = item[1].split()
			full_term = temp[0] + '_' + temp[1]
			boss_name = item[2]

		# get the boss' name if possible
		if boss_name != None:
			boss_lowercase = boss_name.lower()
		
		if (boss_lowercase.islower()):		# check that the name has valid characters
			addBoss(full_term, boss_name, isSkill=isSkill)		# Add boss to the tree

		send_data['nodes'].append({"id": full_term, "group":1})				# add the name as a node to the list of nodes
		temp_dict = {"source": full_term, "target": base_node, "value":1}	# add person-to-base-node link
		send_data['links'].append(temp_dict)

		

# This route is what the user sees when they first visit the `/` URL
@app.route('/')
def index():
	return render_template(WP_INDEX)	# Renders the file located under .../templates/index.html

# This route is the page the users accesses after they log into their account	
@app.route('/organizer_tool', methods=['GET','POST'])
@oidc.require_login		# requires Okta login
def organizer():
	
	# make sure we can access the variables we need
	global send_data
	global previously_searched
	global previous_result
	global multi_list_src
	full_term = ""		# the full term that gave results from the DB; used when the query is one word long
	boss_name = ""		# the higher-up who the query (if they're a person) reports to
	global result		# FIXME
	global node_num_flag
	global render_back_bttn
	global name
	is_mult_list = False	# flag used to make searches taken from the drop-down name list only display one layer of names
	

	# determine how we should respond to POST requests
	if request.method == 'POST':
		
		# process input from the 'go' button
		if request.form['go'] == 'GO':
			
			search_q = request.form.get('search_text')			# get the user's search query from the front-end

			# check to see if we have a valid query from the user
			if (search_q != None) and (search_q != ""):
				item_name = ""
				delim_q = search_q.split()						# create a delimited version of the user's query
				if len(delim_q) > 1:							# if the query got delimited
					item_name = delim_q[0] + '_' + delim_q[1]	# use delimiters to create the person's name
				else:
					item_name = search_q						# else, just use the query itself in the search
				
				if (previously_searched != item_name):			# check if we're searching again for the previous search
					
					# make sure our tree is empty
					send_data['nodes'] = []
					send_data['links'] = []

					# search for query in name column of DB
					result = searchDB(search_term=search_q, column="userName", table=TABLE_TO_USE, fetchAll=True)

					# identify if multiple names have been found for a single search and set result to just the first name
					if len(result) > 1:
						#FIXME
						# print('!!!			MULTIPLE NAMES HAVE BEEN FOUND FOR A SINGLE SEARCH			!!!')
						# print('here is the tuple in question:\n', json.dumps(result, indent=3))
						#FIXME
						multi_list_src = result
						result = result[0]

					# if we have a result from the names column, make the tree
					if result:

						# get the full term (person's name) from the column of search from the first result
						if len(result) > 1:
							t0 = result
							temp = t0[1].split()
							is_mult_list = True
						else:
							multi_list_src = None
							t0 = result[0]
							temp = t0[1].split()	
							is_mult_list = False		

						full_term = temp[0] + '_' + temp[1]	

						addUser(t0, full_term, is_mult_list=is_mult_list)	# create the tree we'll render

						previously_searched = full_term		# mark search as previously searched
						previous_result = result			# mark down the search result

						# render again with the new tree
						render_back_bttn = True
						return render_template(WP_DASH, search_q=search_q, result=result, node_num_flag=node_num_flag, multi_list_src=multi_list_src,
												render_back_bttn=render_back_bttn )

					# check custom DB for result in the title/position column
					result = searchDB(search_term=search_q, column="position", table=CUST_DAT, fetchAll=True)
					if result:
						peopleOnNode(result=result, base_node=search_q, isSkill=True)
						render_back_bttn = True
						return render_template(WP_DASH, search_q=search_q, result=result, node_num_flag=node_num_flag, render_back_bttn=render_back_bttn)

					# check custom DB for result in the skills column
					# I'm assuming there is only one skill that is being searched for, thus no delimiting
					result = searchDB(search_term=search_q, column="skills", table=CUST_DAT, fetchAll=True)
					
					# if we get a result from the skills column, make the tree
					# Again,I'm assuming there is only one skill that is being searched for, thus no delimiting
					if result:
						peopleOnNode(result, search_q, isSkill=True)

						# render again with the new tree
						render_back_bttn = True
						return render_template(WP_DASH, search_q=search_q, result=result, node_num_flag=node_num_flag, render_back_bttn=render_back_bttn)

					
					# check hierarchical DB for result in the orgName column
					result = searchDB(search_term=search_q, column="orgName", table=TABLE_TO_USE, fetchAll=True)
					
					# if we get a result from the orgname column, make the tree
					if result:				
						base_node = "\"" + search_q + "\""
						peopleOnNode(result=result, base_node=base_node)
						
						# render again with the new tree
						render_back_bttn = True
						return render_template(WP_DASH, search_q=search_q, result=result, node_num_flag=node_num_flag, render_back_bttn=render_back_bttn)

					# we don't get a result from any DB
					else:
						multi_list_src = None
						return render_template(WP_DASH, search_q=search_q, result="", node_num_flag=node_num_flag, render_back_bttn=render_back_bttn)
				
			
			# we don't have a valid query from the user
			else:
				# make sure our tree is empty
				send_data['nodes'] = []
				send_data['links'] = [] 
				multi_list_src = None
				return render_template(WP_DASH, search_q="", result="", node_num_flag=node_num_flag, render_back_bttn=render_back_bttn)
			
		# process "submit" button for custom data added by the user
		elif request.form['go'] == 'submit_cust_data':
			global node

			# used for going between formatted column names and the column names stored in the DB
			formatted_column_names = [None, "Position", "Email", "Skills", "Team Description", "Distros", "Sharepoints"]
			column_names = ["user", "position", "email", "skills", "team_dscrp", "distros", "share_pnts"]


			# get the column selection
			selection = request.form.get('col_sel')

			temp_index = formatted_column_names.index(selection)
			selection = column_names[temp_index]

			# get custom data submitted by the user
			custom_data = request.form.get('cust_data').replace("\'", "\'\'")
			
			s = f'UPDATE {DB_TO_USE}.{CUST_DAT} SET {selection}=\'{custom_data}\' where user=\'{node}\''

			cursor.execute(s)
			conn.commit()		# commit DB changes

			return render_template(WP_DASH, search_q=previously_searched, result=previous_result, render_back_bttn=render_back_bttn)
		
		# process "submit" button to add an entry for the node in the custom DB
		elif request.form['go'] == 'req_cust_data':
			s = f'INSERT into {DB_TO_USE}.{CUST_DAT} values("{node}", "", "", "", "", "", "")'
			cursor.execute(s)	# add custom data entry for the node
			conn.commit()		# commit DB changes
			return render_template(WP_DASH, search_q=previously_searched, result=previous_result)

		# process "submit" button to visit the selected node's page	
		elif request.form['go'] == 'visit_node_page':
			
			# make sure our tree is empty
			send_data['nodes'] = []
			send_data['links'] = []

			# special case for selecting a "Reports_To:" node
			#FIXME ---> this is the result of a larger bug in the way we deal with boss names
			node = node.strip()
			#FIXME

			# clean the name of any white space
			if " " in node:
				temp = node.split(" ")
				node = temp[1] + "_" + temp[2]

			# search for query in name column of DB
			result = searchDB(search_term=node, column="userName", table=TABLE_TO_USE, fetchOne=True)
			addUser(result=result, full_term=node)

			previously_searched = node			# mark search as previously searched
			previous_result = result			# mark down the search result

			# render again with the new tree
			return render_template(WP_DASH, search_q=node, result=result, render_back_bttn=render_back_bttn)

		# process "submit" button to visit a name from the drop-down for multiple search results
		elif request.form['go'] == 'submit_multi_name':
			
			# get name as selected by the drop-down menu
			name = request.form.get('mult_list')
			# name = n0[0]

			# make sure our tree is empty
			send_data['nodes'] = []
			send_data['links'] = []

			# search for query in name column of DB
			result = searchDB(search_term=name, column="userName", table=TABLE_TO_USE, fetchOne=True)

			# get the full term (person's name) from the column of search from the first result
			temp = result[1].split()
			full_term = temp[0] + '_' + temp[1]	

			addUser(result, full_term, is_mult_list=True)				# create the tree we'll render

			previously_searched = full_term			# mark search as previously searched
			previous_result = result				# mark down the search result

			# render again with the new tree
			return render_template(WP_DASH, search_q=name, result=result, node_num_flag=node_num_flag, multi_list_src=multi_list_src,
									render_back_bttn=render_back_bttn)

	# determine how we should respond to GET requests
	elif request.method == 'GET':
		global email
		global TOP_NODE
		group = 0

		# make sure our tree is empty
		send_data['nodes'] = []
		send_data['links'] = []

		# search for the user's name in the custom_data DB
		# s = f'SELECT * from {DB_TO_USE}.{CUST_DAT} where email like \'%{email}%\''
		s = f'SELECT * from {DB_TO_USE}.{TABLE_TO_USE} where userName like \'%{name}%\''
		cursor.execute(s)
		result = cursor.fetchone()

		# find the user in the main hierarchical .csv
		if result != None:
			# create user's name
			temp = result[0].split("_")
			item_name = temp[1] + "_" + temp[2]
			s = f'SELECT * from {DB_TO_USE}.{TABLE_TO_USE} where uniqueID like \'%{item_name}%\''
			cursor.execute(s)

		# if they're not found in the .csv, show the max'd out tree
		else: 
			# create user's name
			item_name = TOP_NODE
			s = f'SELECT * from {DB_TO_USE}.{TABLE_TO_USE} where uniqueID like \'%{ TOP_NODE }%\''
			cursor.execute(s)
		result = cursor.fetchone()

		# create a tree from the user's Okta info
		addUser(result, item_name)
		
		# render the webpage with the tree generated from the login user's credentials
		return render_template(WP_DASH, search_q=None, result=None, data=None)
	
	# load the dashboard page by default
	return render_template(WP_DASH, search_q=None, result=None)



# this route serves the JSON data that we generate from the DB upon a successful search
@app.route('/json')
def giveJSON():
	global send_data
	return json.dumps(send_data)

# when a node is clicked, this route serves data about that node to the front-end
@app.route('/node_data')
def giveNodeData():
	# get the name of the node that's embedded in the front-end's POST request
	global node
	global isCustData
	global email
	global name
	node = request.args.get('node')
	column_names = None
	nodeUserMatches = False		# used to check if the user is allowed to edit the current node

	# column names used for custom data drop-down menu
	formatted_column_names = [None, "Position", "Email", "Skills", "Team Description", "Distros", "Sharepoints"]

	# special case for "Reports_To:" nodes
	if ":" in node:
		node = node.split(":")[1]

	# search selected node's name in the DB
	search_result = searchDB(search_term=node, column="uniqueID", table=TABLE_TO_USE, fetchOne=True)
	
	if search_result:
		"""	
			if we have a valid result from the DB, create 
			a dictionary based on the structure of the DB
		"""

		# search for any custom data
		cust_result = searchDB(search_term=node, column="user", table=CUST_DAT, fetchAll=True)
		
		data = {
			# "Unique ID":	search_result[0],
			"Name":			search_result[1],
			"Reports to":	search_result[2],
			"Title":		search_result[3],
			"Location":		search_result[4],
			"Org. Name":	search_result[5]		
		}

		# if we have custom information
		if len(cust_result) != 0:
			
			isCustData = True
			
			if name.replace(" ", "_") == cust_result[0][0]:
				nodeUserMatches = True

			column_names = [i[0] for i in cursor.description]	# get names of columns
																# note to self: we expect only one entry--therefore one result--for a node (person)
			for item in cust_result:							# go through each entry in the search result
				for i in range(len(item)):	
					data[formatted_column_names[i]] = item[i]				# add custom data to dictionary
			
			# modify outgoing data if necessary 
			data["Title"] = (cust_result[0][1] if cust_result[0][1] else search_result[3])
			data["Postion"] = (None if data["Title"] == data["Position"] else data["Position"])	# removes the redundancy of `title` and `position` matching

		else:
			isCustData = False
	else:
		data = None

	return render_template("/2D_front_end/node_details.html", data=data, column_names=column_names, isCustData=isCustData, 
							node=node, col_name_len=( range(1, len(column_names) if column_names else 1) ), nodeUserMatches=nodeUserMatches,
							formatted_column_names=formatted_column_names) 


@app.route("/login")
@oidc.require_login
def login():

	# retrieve the user's email and name upon login
	global email
	global name
	global previously_searched

	info = oidc.user_getinfo(["email"])
	email = info.get('email')
	
	temp = oidc.user_getinfo(["name"])
	name = temp.get('name')

	# reset search query and redirect to the tool
	previously_searched = ""
	return redirect(url_for('organizer'))


@app.route("/logout")
def logout():
    oidc.logout()
    return redirect(url_for("index"))

if __name__ == "__main__":
	app.run(host='0.0.0.0')

