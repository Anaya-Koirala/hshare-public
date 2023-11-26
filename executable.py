import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import random
import string
from pymongo import MongoClient
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials


class Excel:

    def __init__(self, name):
        self.fname = name
        self.start()

    def start(self):
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


Mongo_client = MongoClient()


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
        return False

    def validate_post_editors(self, post_id):
        post_id = int(post_id)
        self.get_posts()
        editors = []
        if len(self.posts) >= post_id > 0:
            editors.append(self.posts[post_id - 1]['user'])
            for i in self.server_object.get_users():
                if (i['server_role'] == "0" or i['server_role'] == "A") and i['email'] not in editors:
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


class Utils:
    def __init__(self, client=Mongo_client):
        self.client = client

    def all_users(self):
        db = self.client['Users']
        return db.list_collection_names()

    def validate_user_password(self, email):
        db = self.client['Users']
        if email in self.all_users():
            coll = db[email]
            return [encode_decode(i['password'], decode=True) for i in coll.find({})][0]

    def get_all_servers(self):
        return [i for i in self.client.list_database_names() if
                i.lower() != "users" and i.lower() != "local" and i.lower() != "admin"]


def send_verification_code(email, code):
    try:
       #sender = ""
        #password = ""
        html = """<!DOCTYPE html>
        <html>

        <head>
            <title></title>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <meta http-equiv="X-UA-Compatible" content="IE=edge" />
            <style type="text/css">
                @media screen {
                    @font-face {
                        font-family: 'Lato';
                        font-style: normal;
                        font-weight: 400;
                        src: local('Lato Regular'), local('Lato-Regular'), url(https://fonts.gstatic.com/s/lato/v11/qIIYRU-oROkIk8vfvxw6QvesZW2xOQ-xsNqO47m55DA.woff) format('woff');
                    }

                    @font-face {
                        font-family: 'Lato';
                        font-style: normal;
                        font-weight: 700;
                        src: local('Lato Bold'), local('Lato-Bold'), url(https://fonts.gstatic.com/s/lato/v11/qdgUG4U09HnJwhYI-uK18wLUuEpTyoUstqEm5AMlJo4.woff) format('woff');
                    }

                    @font-face {
                        font-family: 'Lato';
                        font-style: italic;
                        font-weight: 400;
                        src: local('Lato Italic'), local('Lato-Italic'), url(https://fonts.gstatic.com/s/lato/v11/RYyZNoeFgb0l7W3Vu1aSWOvvDin1pK8aKteLpeZ5c0A.woff) format('woff');
                    }

                    @font-face {
                        font-family: 'Lato';
                        font-style: italic;
                        font-weight: 700;
                        src: local('Lato Bold Italic'), local('Lato-BoldItalic'), url(https://fonts.gstatic.com/s/lato/v11/HkF_qI1x_noxlxhrhMQYELO3LdcAZYWl9Si6vvxL-qU.woff) format('woff');
                    }
                }

                /* CLIENT-SPECIFIC STYLES */
                body,
                table,
                td,
                a {
                    -webkit-text-size-adjust: 100%;
                    -ms-text-size-adjust: 100%;
                }

                table,
                td {
                    mso-table-lspace: 0pt;
                    mso-table-rspace: 0pt;
                }

                img {
                    -ms-interpolation-mode: bicubic;
                }

                /* RESET STYLES */
                img {
                    border: 0;
                    height: auto;
                    line-height: 100%;
                    outline: none;
                    text-decoration: none;
                }

                table {
                    border-collapse: collapse !important;
                }

                body {
                    height: 100% !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    width: 100% !important;
                }

                /* iOS BLUE LINKS */
                a[x-apple-data-detectors] {
                    color: inherit !important;
                    text-decoration: none !important;
                    font-size: inherit !important;
                    font-family: inherit !important;
                    font-weight: inherit !important;
                    line-height: inherit !important;
                }

                /* MOBILE STYLES */
                @media screen and (max-width:600px) {
                    h1 {
                        font-size: 32px !important;
                        line-height: 32px !important;
                    }
                }

                /* ANDROID CENTER FIX */
                div[style*="margin: 16px 0;"] {
                    margin: 0 !important;
                }
            </style>
        </head>""" + f"""
        <body style="background-color: #f4f4f4; margin: 0 !important; padding: 0 !important;">
            <!-- HIDDEN PREHEADER TEXT -->
            <div style="display: none; font-size: 1px; color: #fefefe; line-height: 1px; font-family: 'Lato', Helvetica, Arial, sans-serif; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden;"> We're thrilled to have you here! Get ready to dive into your new account. </div>
            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                <!-- LOGO -->
                <tr>
                    <td bgcolor="#FFA73B" align="center">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                            <tr>
                                <td align="center" valign="top" style="padding: 40px 10px 40px 10px;"> </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td bgcolor="#FFA73B" align="center" style="padding: 0px 10px 0px 10px;">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                            <tr>
                                <td bgcolor="#ffffff" align="center" valign="top" style="padding: 40px 20px 20px 20px; border-radius: 4px 4px 0px 0px; color: #111111; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 48px; font-weight: 400; letter-spacing: 4px; line-height: 48px;">
                                    <h1 style="font-size: 48px; font-weight: 400; margin: 2;">Welcome!</h1> <img src=" https://img.icons8.com/clouds/100/000000/handshake.png" width="125" height="120" style="display: block; border: 0px;" />
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td bgcolor="#f4f4f4" align="center" style="padding: 0px 10px 0px 10px;">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                            <tr>
                                <td bgcolor="#ffffff" align="left" style="padding: 20px 30px 40px 30px; color: #666666; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 400; line-height: 25px;">
                                    <p style="margin: 0;">We're excited to have you get started. First, you need to confirm your account</p>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#ffffff" align="left">
                                    <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                        <tr>
                                            <td bgcolor="#ffffff" align="center" style="padding: 20px 30px 60px 30px;">
                                                <table border="0" cellspacing="0" cellpadding="0">
                                                    <tr>
                                                        <td align="center" style="border-radius: 3px;" bgcolor="#FFA73B"><p style="font-size: 20px; font-family: Helvetica, Arial, sans-serif; color: #ffffff; text-decoration: none; color: #ffffff; text-decoration: none; padding: 15px 25px; border-radius: 2px; border: 1px solid #FFA73B; display: inline-block;">Verification Code:<br>{code}</p></td>
                                                    </tr>
                                                </table>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#ffffff" align="left" style="padding: 0px 30px 20px 30px; color: #666666; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 400; line-height: 25px;">
                                    <p style="margin: 0;">If you have any questions, just reply to this email, we are always ready to help out.</p>
                                </td>
                            </tr>
                            <tr>
                                <td bgcolor="#ffffff" align="left" style="padding: 0px 30px 40px 30px; border-radius: 0px 0px 4px 4px; color: #666666; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 400; line-height: 25px;">
                                    <p style="margin: 0;">Cheers,<br>HShare</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td bgcolor="#f4f4f4" align="center" style="padding: 30px 10px 0px 10px;">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                            <tr>
                                <td bgcolor="#FFECD1" align="center" style="padding: 30px 30px 30px 30px; border-radius: 4px 4px 4px 4px; color: #666666; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 18px; font-weight: 400; line-height: 25px;">
                                    <h2 style="font-size: 20px; font-weight: 400; color: #111111; margin: 0;">Need more help?</h2>
                                    <p style="margin: 0;"><a href="mailto:krhomeworksite@gmail.com" target="_blank" style="color: #FFA73B;">We&rsquo;re here to help you out</a></p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
                <tr>
                    <td bgcolor="#f4f4f4" align="center" style="padding: 0px 10px 0px 10px;">
                        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px;">
                            <tr>
                                <td bgcolor="#f4f4f4" align="left" style="padding: 0px 30px 30px 30px; color: #666666; font-family: 'Lato', Helvetica, Arial, sans-serif; font-size: 14px; font-weight: 400; line-height: 18px;"> <br>
                                    <p align="center" style="margin: 0;"><small>&copy;KRSOFT</small></p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>

        </html>"""
        message = MIMEMultipart("alternative")
        message["Subject"] = "Email Verification"
        message["From"] = sender
        message["To"] = email
        part1 = MIMEText(html, "html")
        message.attach(part1)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(
                sender, email, message.as_string()
            )
    except Exception as e:
        return e


def rand_pass():
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    num = "0123456789"
    generate_pass = ''.join(
        [random.choice(uppercase + lowercase + num) for _ in range(10)])
    return generate_pass


e = Excel('Admins')
e.get()
admins = e.admins
admin = False
backup = e.password


def make_server(serverName, Channels: list, owner="#", password=None):
    server = ServerUtils(serverName, owner=owner)
    for i in Channels:
        post = Posts(i, server)
    if password is not None:
        details = ServerDetails(server)
        details.add(password)
    ServerUtils(serverName, owner="#")
    return True


def main():
    server_name = input("Enter the server name : ")
    channel_number = int(input("How many channel do you want : "))
    channels = []
    for i in range(channel_number):
        channel = input("Enter channel name : ")
        channels.append(channel)
    password = int(input("Do you want to keep password?\n(1)Yes\n(2)No\n"))
    if password == 1:
        passw = input("Enter server password: ")
        make_server(server_name, channels, password=passw)
    else:
        make_server(server_name, channels)
    print("Server Created")


email = input("Hey! welcome, \nFirst lets verify you're admin.\nEnter your email: ")
if email.lower() in admins:
    code = rand_pass()
    send_verification_code(email, code)
    c = input('Enter verification code: ')
    if c == code or c == backup:
        print("Successfully verified")
        admin = True
    else:
        print("Verification Failed")

if admin:
    cont = True
    while cont:
        main()
        continue_ = int(input("Add another?\n(1)Yes\n(2)No\n>"))
        if continue_ != 1:
            cont = False
