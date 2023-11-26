from flask import Flask, render_template, redirect, request, session, g, url_for
from datetime import timedelta
from db import *
from email_client import send_verification_code, rand_pass

app = Flask(__name__)
app.secret_key = '#'
app.permanent_session_lifetime = timedelta(days=15)
utils = Utils()


@app.before_request
def before():
    if 'user' in session:
        g.user = User(session['user'])


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        if utils.validate_user_password(email) == password:
            session.permanent = True
            session['user'] = email
            return redirect('/profile')
        else:
            return "Invalid Password"
    if 'user' in session:
        session.pop('user')
    return render_template('login.html')


@app.route('/logout')
def logout():
    if 'user' in session:
        session.pop('user')
    return redirect(url_for('login'))


@app.route('/signup')
def signup():
    return render_template('signup.html')


@app.route('/signup/verification', methods=['POST'])
def signup_verification():
    if 'signup_code' not in session:
        email = request.form.get('email')
        password = request.form.get('password')
        code = rand_pass()
        session['signup_code'] = code
        session['signup_email'] = email
        session['signup_pass'] = password
        send_verification_code(email, code)
        return render_template("signup.html")
    code = request.form.get('code')
    if code == session['signup_code']:
        User(session['signup_email'], password=session['signup_pass'])
        session.pop('signup_code')
        session.pop('signup_pass')
        session.pop('signup_email')
        return redirect("/login")
    return "Invalid Verification Code"


@app.route('/profile')
def profile():
    if 'user' in session:
        return render_template('Profile.html')
    else:
        return redirect('/login')


if __name__ == "__main__":
    app.run()
