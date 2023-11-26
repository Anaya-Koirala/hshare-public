# imports

from flask import Flask, render_template, redirect, url_for, session, request, g, abort, flash, make_response
from urllib.parse import urlparse
from datetime import timedelta
from db import *
import datetime
from email_client import *
import os
from file import upload_file

# initialization

app = Flask(__name__)
app.secret_key = 'ae4533e4c16c3789ee7233c35846f47a'
app.permanent_session_lifetime = timedelta(days=15)
utils = Utils()
admin_tasks = ['allmembers', 'members', "details", "delete server"]
excel = Excel('Admins')
pageAdminTasks = ['allusers', 'createserver', 'blogs', 'createblogs']
BlogDb = BlogsDb()
notes = NotesDb()


def page_not_found(e):
    return render_template('404.html'), 404


def serverError(e):
    return render_template('500.html'), 500


app.register_error_handler(404, page_not_found)


# Web Pages Routes

@app.route("/")
def main():
    return render_template('index.html', title="Home")


@app.route('/about')
def about():
    return render_template('about.html', title="About")


# sitemap
@app.route("/sitemap")
@app.route("/sitemap/")
@app.route("/sitemap.xml")
def sitemap():
    host_components = urlparse(request.host_url)
    host_base = host_components.scheme + "://" + host_components.netloc
    ten_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).date().isoformat()
    # Static routes with static content
    static_urls = list()
    for rule in app.url_map.iter_rules():
        if not str(rule).startswith("/admin") and not str(rule).startswith("/user"):
            if "GET" in rule.methods and len(rule.arguments) == 0:
                url = {
                    "loc": f"{host_base}{str(rule)}",
                    "lastmod": ten_days_ago
                }
                static_urls.append(url)

    # Dynamic routes with dynamic content
    dynamic_urls = list()
    blog_posts = BlogDb.allBlogs()
    for post in blog_posts:
        url = {
            "loc": f"{host_base}/blog/{post['id']}",
            "lastmod": ten_days_ago
        }
        dynamic_urls.append(url)
    for server in utils.get_all_servers():
        url = {
            "loc": f"{host_base}/servers/{server}",
            "lastmod": ten_days_ago
        }
        dynamic_urls.append(url)
        server = ServerUtils(server)
        for channel in server.get_all_channels():
            posts = Posts(channel, server).get_posts()
            for i in posts:
                url = {
                    "loc": f"{host_base}/servers/{server.server_name}/{channel}/{i['id']}",
                    "lastmod": ten_days_ago
                }
                dynamic_urls.append(url)

    for i in ['grade9', 'grade10']:
        url = {
            "loc": f"{host_base}/notes/{i}",
            "lastmod": ten_days_ago
        }
        dynamic_urls.append(url)

    xml_sitemap = render_template("sitemap.xml", static_urls=static_urls, dynamic_urls=dynamic_urls,
                                  host_base=host_base)
    response = make_response(xml_sitemap)
    response.headers["Content-Type"] = "application/xml"

    return response


# routes related to login and signup


@app.route('/signup', methods=['POST', 'GET'])
def signup():
    if "signup_code" in session:
        session.pop('signup_code')
        session.pop('signup_pass')
        session.pop('signup_email')
    return render_template('signup.html', title="SignUp")


@app.route('/signup/verification', methods=['POST'])
def signup_verification():
    email = request.form.get('email')
    if 'signup_code' not in session:
        if email.lower() not in utils.all_users():
            password = request.form.get('password')
            code = rand_pass()
            session['signup_code'] = code
            session['signup_email'] = email
            session['signup_pass'] = password
            send_verification_code(email, code)
            return render_template("signup.html", title="Register")
        else:
            return redirect('/login')
    code = request.form.get('code')
    if code == session['signup_code']:
        User(session['signup_email'], password=session['signup_pass'])
        session.pop('signup_code')
        session.pop('signup_pass')
        session.pop('signup_email')
        return redirect("/login"), flash('Signed Up Successfully', 'info')
    session.pop('signup_code')
    session.pop('signup_pass')
    session.pop('signup_email')
    return redirect("/signup"), flash('Invalid Verification Code', 'danger')


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        if email in utils.all_users():
            if utils.validate_user_password(email) == password:
                session.permanent = True
                session['user'] = email
                return redirect('/profile'), flash('Logged in Successfully', 'info')
            else:
                return redirect('/login'), flash('Wrong Password', 'danger')
        else:
            redirect('/login'), flash('No Such Account Exists', 'danger')
    if 'user' in session:
        return redirect('/logout')
    return render_template('login.html', title="Login")


@app.route('/logout', methods=['GET'])
def logout():
    if 'user' in session:
        session.clear()
        return redirect(url_for('login')), flash('Logged Out Successfully', 'info')


@app.route('/forgotPassword', methods=['GET', 'POST'])
def forgotPassword():
    if request.method == "POST":
        if 'forgot_email' not in session:
            email = request.form.get('email')
            passwordRecoveryCode = rand_pass()
            if email.lower() in utils.all_users():
                send_passwordReset_code(email, passwordRecoveryCode)
                session['forgot_email'] = email
                session['forgot_code'] = passwordRecoveryCode
                return render_template("forgotPassword.html", title="Forget Password")
            else:
                return flash('Invalid Email', 'danger')
        else:
            code = request.form.get('verificationCode')
            newPassword = request.form.get('newPass')
            if code == session['forgot_code']:
                user = User(session['forgot_email'])
                user.update_user_password(newPassword)
                session.pop('forgot_email')
                session.pop('forgot_code')
            else:
                session.pop('forgot_email')
                session.pop('forgot_code')
                return "Invalid Verification Code"
            return redirect(url_for('login'))
    if "forgot_code" in session:
        session.pop('forgot_email')
        session.pop("forgot_code")
    return render_template("forgotPassword.html", title="Forget Password")


# routes related to profile


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        return redirect('/login')
    if request.method == "GET":
        return render_template('Profile.html', title="Profile")
    delete = request.form.get('delete')
    if delete == "1":
        g.user.purgeUser()
        return redirect('/login')
    elif delete == "0":
        current_pass = request.form.get('current')
        if current_pass == utils.validate_user_password(g.user.email):
            g.user.update_user_password(request.form.get('new'))
            return redirect('/profile')
        else:
            return "Invalid Current Password"


# routes related to servers


@app.route('/servers')
def serverHomePage():
    public_servers = ['Science', "Maths", "English", "SocialStudies", "Nepali", "Others"]
    allservers = [i for i in utils.get_all_servers() if i not in public_servers]
    return render_template("servers.html", allServers=allservers, public=public_servers, title="Servers")


@app.route('/joinserver/<serverName>', methods=["POST", "GET"])
def joinserver(serverName):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName in utils.get_all_servers():
        if serverName in g.user.get_servers():
            return redirect(f"/servers/{serverName}")
    else:
        flash('Server Not Found', 'danger')
    server = ServerUtils(serverName)
    details = ServerDetails(server).get_server_details()
    if request.method == "POST":
        password = request.form.get('password')
        if details == password:
            g.user.add_server(serverName)
            return redirect(url_for('profile'))
        else:
            return redirect(f'/joinserver/{serverName}'), flash('Wrong Password', 'danger')
    if not details:
        g.user.add_server(serverName)
        return redirect(url_for('profile'))
    return render_template('joinServer.html', title="Join Servers", server=serverName)


@app.route('/servers/<serverName>/leave')
def leave_server(serverName):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName in utils.get_all_servers():
        server = ServerUtils(serverName)
        serUser = server.valid_server_user(g.user.email)
        if serUser:
            if serUser['server_role'] != "O":
                g.user.remove_server(server.server_name)
            else:
                return redirect(f'/servers/{serverName}'), flash('You are the owner', 'danger')
            return redirect(url_for('profile'))
        else:
            return redirect(url_for('serverHomePage')), flash('Not Part Of This Server', 'danger')
    else:
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')


@app.route('/servers/<serverName>')
def server_home(serverName):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName in utils.get_all_servers():
        server = ServerUtils(serverName)
        if server.valid_server_user(g.user.email):
            return render_template('serverHome.html', server=server, title=f"{serverName}", serverName=serverName)
        else:
            return redirect(f'/joinserver/{serverName}')
    else:
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')


@app.route('/servers/<serverName>/<channelName>', methods=['GET', 'POST'])
@app.route('/servers/<serverName>/<channelName>/<page>', methods=['GET', 'POST'])
def channel_home(serverName, channelName, page=None):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName not in utils.get_all_servers():
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    else:
        server_ = ServerUtils(serverName)
        if not server_.valid_server_user(g.user.email):
            return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    if channelName not in server_.get_all_channels():
        return redirect(url_for(f'/servers/{serverName}')), flash('Channel Doesnot Exist', 'danger')
    posts = Posts(channelName, server_)
    allPosts = posts.posts
    allPosts.reverse()
    if request.method == "GET":
        if page is not None:
            current = int(page)
            page = int(page) * 10
            if page > 0:
                if page <= len(allPosts):
                    post = allPosts[page - 10: page]
                elif page - 10 < len(allPosts) < page:
                    post = allPosts[page - 10:]
                else:
                    return redirect(f"/servers/{serverName}/{channelName}")
            else:
                return redirect(f"/servers/{serverName}/{channelName}")
        else:
            current = 1
            if len(allPosts) > 10:
                post = allPosts[:10]
            else:
                post = allPosts
        return render_template('channel.html', posts=posts, displayPosts=post, prev=current - 1, next=current + 1,
                               url=f"servers/{serverName}/{channelName}", serverName=serverName, current=current)
    title = request.form.get('title')
    desc = request.form.get('desc')
    file = request.files['file']
    if file.filename != "":
        _, file_type = check_fileName(file.filename)
        if _:
            filename = str(datetime.datetime.now().timestamp()
                           ).split('.')[0] + file_type
            file.save(filename)
            fileUrl = upload_file(filename)
            os.remove(filename)
        else:
            return redirect(f'/servers/{serverName}/{channelName}'), flash(
                'File Type Not Support ( only pdf , pptx , txt , docx, xlsx are supported for now )', 'danger')
    else:
        fileUrl = False
    if fileUrl:
        posts.add_post(title, desc, fileUrl, g.user.email)
    else:
        posts.add_post(title, desc, "NONE", g.user.email)
    return redirect(request.url)


@app.route('/servers/<serverName>/<channelName>/delete/<post_id>')
def delete_post(serverName, channelName, post_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName not in utils.get_all_servers():
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    else:
        server_ = ServerUtils(serverName)
        if not server_.valid_server_user(g.user.email):
            return redirect(url_for('serverHomePage')), flash('Not A Part of This Server', 'danger')
    if channelName not in server_.get_all_channels():
        return redirect(url_for(f'/servers/{serverName}')), flash('Channel Doesnot Exist', 'danger')
    posts = Posts(channelName, server_)
    deleted = posts.delete_post(int(post_id), g.user.email)
    if not deleted:
        return abort(403)
    else:
        return redirect(f"/servers/{serverName}/{channelName}")


@app.route('/servers/<serverName>/<channelName>/posts/<post_id>')
def view_post(serverName, channelName, post_id):
    server_ = ServerUtils(serverName)
    details = ServerDetails(server_).get_server_details()
    if 'user' not in session:
        if details:
            return redirect('/login')
        if serverName not in utils.get_all_servers():
            return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    else:
        if serverName not in utils.get_all_servers():
            return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
        if not server_.valid_server_user(g.user.email):
            if details:
                return redirect(url_for('serverHomePage')), flash('Not A Part of This Server', 'danger')
            return redirect(f'/joinserver/{serverName}')
    if channelName not in server_.get_all_channels():
        return redirect(f'/servers/{serverName}'), flash('Channel Doesnot Exist', 'danger')
    posts = Posts(channelName, server_).posts
    post_id = int(post_id)
    if 0 < post_id <= len(posts):
        post = posts[post_id - 1]
        return render_template('post.html', post=post, title="Post", url=f"servers/{serverName}/{channelName}",
                               serverName=serverName)
    return abort(404)


@app.route('/servers/<serverName>/admin')
def serverAdmin(serverName):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName not in utils.get_all_servers():
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    else:
        server_ = ServerUtils(serverName)
        server_user = server_.valid_server_user(g.user.email)
        if not server_user:
            return redirect(url_for('serverHomePage')), flash('Not A Part of This Server', 'danger')
        elif server_user['server_role'] != "O" and server_user['server_role'] != "A":
            return redirect(url_for(f'/servers/{serverName}')), flash('Forbidden', 'danger')
    global admin_tasks
    return render_template("serverAdmin.html", tasks=admin_tasks, serverName=serverName, title="Admin Tasks")


@app.route('/servers/<serverName>/admin/<task>', methods=['POST', 'GET'])
def serverAdminFunctions(serverName, task):
    if 'user' not in session:
        return redirect(url_for('login'))
    if serverName not in utils.get_all_servers():
        return redirect(url_for('serverHomePage')), flash('Server Not Found', 'danger')
    else:
        server_ = ServerUtils(serverName)
        server_user = server_.valid_server_user(g.user.email)
        if not server_user:
            return redirect(url_for('serverHomePage')), flash('Not A Part of This Server', 'danger')
        elif server_user['server_role'] != "O" and server_user['server_role'] != "A":
            return redirect(url_for(f'/servers/{serverName}')), flash('Forbidden', 'danger')
    global admin_tasks
    if task.lower() not in admin_tasks:
        return f"CANT ({task}) at the momment<br>NO SUCH ADMIN FUNCTION EXISTS"
    if task.lower() == "members":
        if request.method == "GET":
            all_users = server_.get_users()
            return render_template("serverAdminMembers.html", allUsers=all_users, validate=server_.valid_server_user,
                                   serverName=serverName)
        user = server_.valid_server_user(request.form.get('user'))
        if user:
            role = str(request.form.get('role')).upper()
            server_.update_user_role(user['id'], role)
            return redirect(request.url)
    if task.lower() == "allmembers":
        allMembers = server_.get_users()
        return render_template('serverAdminAll.html', allUsers=allMembers, serverName=serverName)
    if task.lower() == "details":
        details = ServerDetails(server_)
        if request.method == "GET":
            return render_template('serverAdminDetails.html', details=details, serverName=serverName)
        password = request.form.get('password')
        if password is not None:
            details.update_server_details(password)
        else:
            if request.form.get('p') is not None:
                details.remove_server_password()
        return redirect(request.url)
    if task.lower() == "delete server":
        if server_user['server_role'].lower() == "o":
            server_.delete_server()
            return redirect('/servers')
        else:
            return abort(403)
    return abort(404)


@app.route('/admin', methods=['POST', 'GET'])
def AdminHome():
    if 'user' not in session:
        return abort(404)
    elif g.user.email.lower() not in excel.get():
        return abort(404)
    if 'pageAdmin' not in session:
        if request.method == "GET":
            return render_template('adminLogin.html')
        password = request.form.get('pass')
        excel.get()
        if password == excel.password:
            session['pageAdmin'] = True
            return redirect('/admin')
        return abort(404)
    return render_template('adminHome.html', tasks=pageAdminTasks)


@app.route('/admin/<adminTask>', methods=['POST', 'GET'])
def AdminTasks(adminTask):
    if 'user' not in session:
        return abort(404)
    elif g.user.email.lower() not in excel.get():
        return abort(404)
    if 'pageAdmin' not in session:
        return redirect('/admin')
    if adminTask.lower() not in pageAdminTasks:
        return abort(404)
    if adminTask.lower() == "allusers":
        if request.method == "GET":
            allUsers = utils.all_users_details()
            return render_template("adminAllMembers.html",
                                   allUsers=[i for i in allUsers if i['email'].lower() not in excel.get()], length=len)
        email = request.form.get('email')
        User(email).purgeUser()
        return redirect(request.url)
    elif adminTask.lower() == "createserver":
        if request.method == "GET":
            return render_template('adminCreateServer.html')
        name = request.form.get('name')
        num = int(request.form.get('num'))
        channels = []
        for i in range(1, num + 1):
            channels.append(request.form.get(f'channel{i}'))
        password = request.form.get('password')
        if password != "":
            make_server(name, channels, password=password)
        else:
            make_server(name, channels)
        return redirect(f'/servers/{name}')
    elif adminTask.lower() == "blogs":
        if request.method == "GET":
            return render_template('admin_blogs.html', blogs=BlogDb.allBlogs())
        NotDelete = request.form.get('delete') == "1"
        BlogID = int(request.form.get('id'))
        if NotDelete:
            title = request.form.get('title')
            code = request.form.get('code')
            BlogDb.updateBlog(BlogID, title, code)
            return redirect('/admin/blogs'), flash(f"Updated Blog with ID : {BlogID}", "success")
        else:
            BlogDb.deleteBlog(BlogID)
            return redirect('/admin/blogs'), flash(f"Deleted Blog Successfully", "success")
    elif adminTask.lower() == "createblogs":
        if request.method == "GET":
            return render_template('admin_blogs_create.html')
        title = request.form.get('title')
        code = request.form.get('code')
        BlogDb.addBlog(title, code)
        return redirect('/admin/blogs'), flash('Successfully created New Blog', "success")


@app.route('/faq')
def Faq():
    return render_template('faq.html', title="Frequently Asked Questions")


@app.route('/contactus', methods=['GET', 'POST'])
def contact():
    if request.method == "POST":
        email = request.form.get('email')
        subject = request.form.get('sub')
        desc = request.form.get('desc')
        sendMessage(f"Support: {subject}", f"By: {email}\n\n{desc}")
        return redirect('/contactus')
    return render_template('contact.html', title="Contact Us")


@app.route('/hof')
@app.route('/HOF')
def hallOfFame():
    return render_template('hallOfFame.html', title="Hall Of Fame")


# various misc functions


@app.before_request
def before():
    if 'user' in session:
        if session['user'] in utils.all_users():
            g.user = User(session['user'])
        else:
            session.pop('user')
    session.permanent = True


# blogs routes


@app.route('/blogs/<int:blog_id>')
def blog(blog_id):
    allBlogs = BlogDb.allBlogs()
    if 0 < blog_id > len(allBlogs):
        return redirect('/blogs'), flash("Blog not found", "danger")
    Blog = allBlogs[blog_id - 1]
    return render_template('blog.html', title=Blog['title'], docCode=Blog['code'])


@app.route('/blogs')
def blogs():
    return render_template('blogs.html', blogs=BlogDb.allBlogs())


# Note Routes


subjects = ['English', "Nepali", "Maths", "Science", "SocialStudies", "EPH", "Computer", "Accountancy", "OptionalMaths",
            "EnvironmentScience"]


@app.route('/notes')
def Notes():
    return render_template('notes.html', title="Notes", subjects=subjects)


@app.route('/notes/<grade>')
def NotesDetails(grade):
    grade = grade.lower()
    if grade not in ['grade9', 'grade10']:
        return redirect('/notes'), flash('No Such Subject or Grade Exists', 'danger')
    allPosts = []
    for i in subjects:
        allPosts.append(notes.specific_Subjects(i, grade))
    return render_template('notesDetails.html', title="Notes", subjects=subjects, allNotes=allPosts)


@app.route('/notes/<grade>/upload', methods=['POST'])
def uploadNotes(grade):
    if 'user' not in session:
        return redirect('/login'), flash('Please Log-In to continue', 'danger')
    else:
        title = request.form.get('title')
        subject = request.form.get('subject')
        user = g.user.email
        grade = grade.lower()
        if subject not in subjects and grade not in ['grade9', 'grade10']:
            return redirect('/notes'), flash('No Such Subject or Grade Exists', 'danger')
        file = request.files['file']
        if file.filename != "":
            _, file_type = check_fileName(file.filename)
            if _:
                filename = str(datetime.datetime.now().timestamp()
                               ).split('.')[0] + file_type
                file.save(filename)
                fileUrl = upload_file(filename)
                os.remove(filename)
            else:
                return redirect('/notes'), flash(
                    'File Type Not Support ( only pdf , pptx , txt , docx, xlsx are supported for now )', 'danger')
        else:
            return redirect('/notes'), flash(
                'Something went wrong with the upload', 'danger')
        notes.addPost(title, fileUrl, user, subject, grade)
        return redirect(f'/notes/{grade}'), flash('Post Uploaded Successfully', 'success')


if __name__ == "__main__":
    app.run(debug=True)
