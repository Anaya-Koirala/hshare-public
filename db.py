from pymongo import MongoClient
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials

#Mongo_client = MongoClient()


def encode_decode(string, decode=False):
    if not decode:
        message_bytes = string.encode('ascii')
        base64_bytes = base64.b64encode(message_bytes)
        base64_message = base64_bytes.decode('ascii')
        return base64_message
    else:
        base64_bytes = string.encode('ascii')
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode('ascii')
        return message


class ServerUtils:

    def __init__(self, dbname, client=Mongo_client, owner=None):
        self.dbname = dbname
        self.client = client
        self.db = self.client[dbname]
        self.collection = self.db['Users']
        self.server_name = dbname
        if owner is not None:
            User(owner).add_server(dbname, role="O")
        self.get_users()

    def get_users(self):
        entries = self.collection.find({})
        self.server_users = [{'id': i['id'], 'email': i['email'],
                              'server_role': i['server_role']} for i in entries]
        return self.server_users

    def valid_server_user(self, email):
        self.get_users()
        for i in self.server_users:
            if i['email'] == email.lower():
                return i
        return False

    def add_server_user(self, email, role="M"):
        self.get_users()
        if email not in [i['email'] for i in self.server_users]:
            if len(self.server_users) > 0:
                self.collection.insert_one(
                    {'id': self.server_users[-1]['id'] + 1, 'email': email, 'server_role': role})
            else:
                self.collection.insert_one(
                    {'id': 1, 'email': email, 'server_role': role})
            self.manage()

    def remove_server_user(self, email):
        if self.valid_server_user(email):
            self.collection.delete_one({'email': email})
        self.manage()

    def manage(self):
        self.get_users()
        user_id = 1
        for i in self.server_users:
            self.collection.update_one(i, {"$set": {'id': user_id}})
            user_id += 1

    def update_user_role(self, user_id, new_role):
        self.collection.update_one(
            {'id': user_id}, {"$set": {'server_role': new_role}})
        self.get_users()

    def get_all_channels(self):
        return [i for i in self.db.list_collection_names() if i != "Users" and i != "Details"]

    def delete_server(self):
        for i in self.get_users():
            User(i['email']).remove_server(self.server_name)
        self.client.drop_database(self.server_name)


class Posts:

    def __init__(self, channel, server_object):
        self.client = server_object.client
        self.db = server_object.db
        self.collection = self.db[channel]
        self.channel = channel
        self.get_posts()
        self.server_object = server_object

    def get_posts(self):
        posts = [i for i in self.collection.find({})]
        if len(posts) > 0:
            self.posts = [{'id': i['id'], 'title': i['title'], 'desc': i['desc'], 'user': i['user'], 'link': i['link']}
                          for
                          i in posts if i['id'] != "message"]
        else:
            self.collection.insert_one({'id': 'message'})
            self.get_posts()
        return self.posts

    def add_post(self, title, desc, link, user):
        self.get_posts()
        if len(self.posts) > 0:
            post = {'id': self.posts[-1]['id'] + 1, 'title': title,
                    'desc': desc, 'user': user, 'link': link}
        else:
            post = {'id': 1, 'title': title,
                    'desc': desc, 'user': user, 'link': link}
        self.collection.insert_one(post)
        self.manage()

    def manage(self):
        self.get_posts()
        post_id = 1
        for i in self.posts:
            self.collection.update_one(i, {"$set": {'id': post_id}})
            post_id += 1

    def delete_post(self, post_id, user):
        if user in self.validate_post_editors(post_id):
            self.get_posts()
            self.collection.delete_one({'id': post_id})
            self.manage()
            return True
        print(self.validate_post_editors(post_id))
        return False

    def validate_post_editors(self, post_id):
        post_id = int(post_id)
        self.get_posts()
        editors = []
        if len(self.posts) >= post_id > 0:
            editors.append(self.posts[post_id - 1]['user'])
            for i in self.server_object.get_users():
                if (i['server_role'].lower() == "o" or i['server_role'].lower() == "a") and i['email'] not in editors:
                    editors.append(i['email'])
        return editors

    def valid_post_editor(self, username, post_id):
        if username in self.validate_post_editors(post_id):
            return True
        else:
            return False


class ServerDetails:

    def __init__(self, server_obj):
        self.server = server_obj
        self.client = self.server.client
        self.db = self.server.db
        self.collection = self.db['Details']

    def add(self, Password):
        self.collection.delete_many({})
        self.collection.insert_one(
            {'server_name': self.server.server_name, 'server_password': Password})

    def get_server_details(self):
        all_details = self.collection.find(
            {'server_name': self.server.server_name})
        details = [detail for detail in all_details]
        if len(details) <= 0:
            return False
        else:
            details = details[0]
        self.server_name = details['server_name']
        self.server_password = details['server_password']
        return self.server_password

    def update_server_details(self, new_pass):
        self.collection.delete_many({})
        server_details = self.get_server_details()
        if not server_details:
            self.add(new_pass)
        else:
            self.collection.update_one({'server_name': self.server_name}, {
                '$set': {'server_password': new_pass}})

    def remove_server_password(self):
        self.collection.drop()


class User:

    def __init__(self, email, client=Mongo_client, password=None):
        self.client = client
        self.db = self.client['Users']
        self.collection = self.db[email]
        if password is not None:
            self.collection.insert_one(
                {'email': email, 'password': encode_decode(password), 'servers': []})
        self.email = email

    def get_servers(self):
        self.servers = []
        servers = [i['servers']
                   for i in self.collection.find({'email': self.email})][0]
        for i in servers:
            all_users = [users['email']
                         for users in ServerUtils(i).get_users()]
            if self.email in all_users:
                self.servers.append(i)
            else:
                self.remove_server(i)
        return self.servers

    def add_server(self, server_name, role="M"):
        self.get_servers()
        server_obj = ServerUtils(server_name, client=self.client)
        server_obj.add_server_user(self.email, role=role)
        self.servers.append(server_name)
        self.collection.update_one({'email': self.email}, {
            '$set': {'servers': self.servers}})

    def update_user_password(self, new_pass):
        self.collection.update_one({'email': self.email}, {
            '$set': {'password': encode_decode(new_pass)}})

    def remove_server(self, server_name):
        servers_list = [i['servers']
                        for i in self.collection.find({'email': self.email})][0]
        if server_name in servers_list:
            servers_list.remove(server_name)
            ServerUtils(server_name).remove_server_user(self.email)
            self.collection.update_one({'email': self.email}, {
                '$set': {'servers': servers_list}})

    def purgeUser(self):
        for i in self.get_servers():
            self.remove_server(i)
        self.db.drop_collection(self.email)


class Utils:
    def __init__(self, client=Mongo_client):
        self.client = client

    def all_users(self):
        db = self.client['Users']
        return [i.lower() for i in db.list_collection_names()]

    def validate_user_password(self, email):
        db = self.client['Users']
        if email in self.all_users():
            coll = db[email]
            return [encode_decode(i['password'], decode=True) for i in coll.find({})][0]
        return False

    def get_all_servers(self):
        return [i for i in self.client.list_database_names() if
                i.lower() != "users" and i.lower() != "local" and i.lower() != "admin" and i.lower() != "miscellaneous"]

    def all_users_details(self):
        db = self.client['Users']
        details = db.list_collection_names()
        userDetails = []
        for i in details:
            user = db[i]
            userD = [{'email': x['email'], 'servers': x['servers']} for x in user.find({})][0]
            userDetails.append(userD)
        return userDetails


class Excel:

    def __init__(self, name):
        self.fname = name
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('adminsVerification.json', scope)
        client = gspread.authorize(creds)
        self.wb = client.open(self.fname)
        self.sheet = self.wb.sheet1
        self.sheet2 = self.wb.worksheet('Sheet2')

    def get(self):
        self.admins = [i for i in self.sheet.col_values(1) if i is not None and i != '']
        self.password = self.sheet2.col_values(1)[0]
        return self.admins


def check_fileName(filename):
    try:
        accepted = ["pdf", "docx", "pptx", "odt", "xlsx", "txt", "text", "ppt", "xls", "doc"]
        file_type = filename.split('.')[-1]
        if file_type.lower() in accepted:
            return True, file_type
    except:
        return False, False
    return False, False


def make_server(serverName, Channels: list, owner="regmiakhu@gmail.com", password=None):
    server = ServerUtils(serverName, owner=owner)
    for i in Channels:
        Posts(i, server)
    if password is not None:
        details = ServerDetails(server)
        details.add(password)
    ServerUtils(serverName, owner="anayakoirala69@gmail.com")
    return True


class NotesDb:
    def __init__(self, client=Mongo_client):
        self.db = client['Miscellaneous']
        self.collection = self.db['Notes']
        self.verified = self.db['verified']

    def verifiedEditors(self):
        return [x['email'] for x in self.verified.find({})]

    def allOrderedPosts(self, grade):
        self.posts = [i for i in self.collection.find({"status": "verified"}, {'_id': 0})] + [i for i in self.collection.find({"status": "unverified"}, {'_id': 0})]
        return self.posts

    def allPosts(self):
        posts = [i for i in self.collection.find({}, {'_id': 0})]
        return posts

    def manage(self):
        posts = self.allPosts()
        post_id = 1
        for i in posts:
            self.collection.update_one(i, {"$set": {'id': post_id}})
            post_id += 1

    def addPost(self, title, link, user, subject, grade, status="unverified"):
        num = len(self.allPosts())
        if user not in self.verifiedEditors():
            self.collection.insert_one(
                {'id': num + 1, 'title': title, "link": link, 'status': status, 'user': user, "subject": subject, "grade": grade})
        else:
            self.collection.insert_one(
                {'id': num + 1, 'title': title, "link": link, 'status': 'verified', 'user': user, "subject": subject, "grade": grade})
        self.manage()

    def delete_post(self, post_id):
        self.collection.delete_one({'id': post_id})
        self.manage()

    def update_post(self, post_id, status="verified"):
        self.collection.update_one({'id': post_id}, {"$set": {'status': status}})
        self.manage()

    def specific_Subjects(self, subject, grade):
        posts = [i for i in self.collection.find({"status": "verified", "subject": subject, "grade": grade}, {'_id': 0})] + [i for i in self.collection.find({"status": "unverified", "subject": subject, "grade": grade}, {'_id': 0})]
        return posts


class BlogsDb:
    def __init__(self, client=Mongo_client):
        self.db = client['Miscellaneous']
        self.collection = self.db['Blogs']

    def allBlogs(self):
        posts = [i for i in self.collection.find({}, {'_id': 0})]
        return posts

    def manage(self):
        posts = self.allBlogs()
        post_id = 1
        for i in posts:
            self.collection.update_one(i, {"$set": {'id': post_id}})
            post_id += 1

    def addBlog(self, title, code):
        num = len(self.allBlogs())
        self.collection.insert_one({'id': num + 1, 'title': title, 'code': code})
        self.manage()

    def updateBlog(self, BlogId, title, code):
        self.collection.update_one({'id': BlogId}, {"$set": {'title': title, 'code': code}})
        self.manage()

    def deleteBlog(self, BlogId):
        self.collection.delete_one({'id': BlogId})
        self.manage()


if __name__ == "__main__":
    pass
