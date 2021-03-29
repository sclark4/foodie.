from flask import (Flask, render_template, make_response, url_for, request,
                   redirect, flash, session, send_from_directory, jsonify)
from werkzeug.utils import secure_filename
app = Flask(__name__)

import cs304dbi as dbi
import menuUpdates as menuUp #module to update foodie database from the menu page
import random
import sys
import pymysql
import feed_queries
import query
import entry

from datetime import date,datetime

app.secret_key = 'your secret here'
# replace that with a random key
app.secret_key = ''.join([ random.choice(('ABCDEFGHIJKLMNOPQRSTUVXYZ' +
                                          'abcdefghijklmnopqrstuvxyz' +
                                          '0123456789'))
                           for i in range(20) ])

# This gets us better error messages for certain common request errors
app.config['TRAP_BAD_REQUEST_ERRORS'] = True
# file upload content 
app.config['UPLOADS'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 1*1024*1024 # 1 MB

def today():
    """Returns a tuple with the string for the current day and time (SQL format)
    and a string for the day/time for display purposes. This is used to primarily to query the database according
    to the lastServed date for a given food item.
    """
    now = date.today()
    return now.strftime("%Y-%m-%d"), now.strftime("%A, %B %d")

@app.route('/pic/<int:fid>') 
#route to image for food photos, can later be generalized and applied to other photos too
def pic(fid):
    conn = dbi.connect()
    curs = dbi.cursor(conn)
    sql = '''select filename from foodPics where fid = %s'''
    curs.execute(sql, [fid])
    try:
        filename = curs.fetchone()[0]
        return send_from_directory(app.config['UPLOADS'],filename)
    except Exception as err: #in the case when there is not yet a photo uploaded
        return None

@app.route('/')
def home():
    # the base template needs only one filler
    return render_template('home.html',title='foodie.')

@app.route('/form/')
def form():
    return render_template('form.html')
@app.route('/mainmenu/')
def mainmenu():
    '''Page with menu and form without any filters'''
    conn = dbi.connect()
    menu = menuUp.lookupMenuList(conn, today()[0])
    return render_template('menu.html',date=today()[1], menu = menu, title ="Menu")

@app.route('/menu/', methods=["GET", "POST"])
def menu():
    conn = dbi.connect()
    if request.method == 'GET':
        # mealtype = ""
        dh = request.args.get('dh-filter', "")
        mealtype = request.args.get("type-filter", "")
        preference = request.args.getlist("preference")
        now = today()[0]
            
        if preference:
            preference = ",".join(preference)
        else:
            preference = ""
        if dh:
            dhName = menuUp.lookupDH(conn, dh)[0]
            waitTime = menuUp.getWaittime(conn, int(dh))[0]
        else:
            dhName = ""
            waitTime = ""
        # IMPLEMENT SEARCH BY LABEL label = ""
        search = request.args["query"]
        # the variable date = today()[] generates the current date to display on the menu page
        if dh == '3' or dh == '4':
            flash("So sorry to be the bearer of bad news, but {} is closed today.".format(dhName))
        if dh or mealtype or preference: #if given a dining hall request and mealtype
            menu = menuUp.filterMenuList(conn, dh, mealtype,preference,now)
        elif search:
            menu = menuUp.searchMenu(conn, search)
            print(menu)
            if len(menu)==1:
                # if there's only one matching result, redirect directly to the food page 
                fid=menu[0]['fid']
                return redirect(url_for('food',fid=int(fid)))
            elif len(menu)==0:
                flash("The name you entered does not match any dish in the databse. \
                    Wold you like to add a new food entry? ")
                return redirect(url_for('addfood'))
            else: 
                flash("Your entry matched multiple entries. Pick from one of the below. ")
        else: #if not given a dining hall request or a mealtype request
            menu = menuUp.lookupMenuList(conn, today()[0])
        return render_template('menu.html',date=today()[1], location = dhName, type = mealtype, menu = menu, title ="Menu", waitTime = waitTime, dh = dh)
    # else: if we decide to add a post method to our menu

#for beta: how do I pass in the fid for processing too? 
@app.route('/autocomplete',methods=['GET'])
def autocomplete():
    conn = dbi.connect()
    # keyword to search: q is from jQuery, looking for 'q'
    search=request.args.get('q')
    # returns a list of dictionary of fid and food name
    dishes=menuUp.searchMenu(conn,search)
    #gets only the food name list 
    results=[entry["name"] for entry in dishes]
    # jsonify makes the list of food names in a JavaScript format
    return jsonify(matching_results=results)

@app.route('/food/<int:fid>', methods=["GET", "POST"])
def food(fid):
    conn = dbi.connect()
    if request.method == 'GET':
        # dictionary containing a food's name, ingredients, preference, allergen, type
        item = menuUp.lookupFoodItem(conn, fid)
        #average rating and number of ratings given to a food item
        avgRating, totalRatings = menuUp.avgRating(conn, fid) 
        # list of dictionaries for each comment for a given food item and with the comment's rating and user
        comments = menuUp.lookupComments(conn, fid)
        filename = pic(fid)
        return render_template('food.html', food = item, comments = comments, fid = fid, rating = avgRating, title = item["name"], filename = filename)

@app.route('/updateFood/<int:fid>', methods=["GET","POST"])
# name, type, rating, description, preference, label
def updateFood(fid):
    conn = dbi.connect()
    if request.method == "GET":
        item = menuUp.lookupFoodItem(conn, fid)
        return render_template('foodUpdate.html', food = item, title = ("Update " + item["name"]))
    elif request.form["submit"] == "update":
        try:
            ingredients = request.form["ingredients"]
            menuUp.updateFoodItem(conn, fid, ingredients)
            item = menuUp.lookupFoodItem(conn, fid)
            flash("Thank you for updating {}, we really appreciate it!".format(item['name']))
            avgRating, totalRatings = menuUp.avgRating(conn, fid)
            comments = menuUp.lookupComments(conn,fid)
            return render_template('food.html', food = item, comments = comments, fid = fid, rating = avgRating)
        except Exception as err:
            flash('Update failed {why}'.format(why=err))
            return render_template('foodUpdate.html', food = item, title = ("Update " + item["name"]))
    else:
        try:
            item = menuUp.lookupFoodItem(conn, fid)
            flash("Thank you for updating {}, we really appreciate it!".format(item['name']))
            avgRating, totalRatings = menuUp.avgRating(conn, fid)
            comments = menuUp.lookupComments(conn,fid)
            f = request.files['pic']
            user_filename = f.filename
            ext = user_filename.split('.')[-1]
            filename = secure_filename('{}.{}'.format(fid,ext))
            pathname = os.path.join(app.config['UPLOADS'],filename)
            f.save(pathname)
            curs = dbi.dict_cursor(conn)
            curs.execute(
                '''insert into foodPics(fid,filename) values (%s,%s)
                   on duplicate key update filename = %s''',
                [fid, filename, filename])
            conn.commit()
            flash('Upload successful.')
            return render_template('food.html', food = item, comments = comments, fid = fid, rating = avgRating)
        except Exception as err:
            flash('Update failed {why}'.format(why=err))
            item = menuUp.lookupFoodItem(conn, fid)
            return render_template('foodUpdate.html', food = item, title = ("Update " + item["name"]))

@app.route('/updateWait/<int:did>', methods=["GET","POST"])
def updateWait(did):
    '''Update waiting time at a given dining hall'''
    conn = dbi.connect()
    dh = menuUp.lookupDH(conn, did)[0]
    if request.method == "GET":
        return render_template('waittimeUpdate.html',did = did, dh = dh, title = ("Update " + dh + " Wait Time"))
    else:
        try:
            waittime = request.form["waittime"]
            menuUp.updateFoodItem(conn, did, waittime)
            flash("Thank you for updating {}'s wait time, we really appreciate it!".format(dh))
            return render_template('menu.html',date=today()[1], menu = menu, title ="Menu")
        except Exception as err:
            flash('Update failed {why}'.format(why=err))
            return render_template('waittimeUpdate.html', dh = dh, did = did, title = ("Update " + dh + " Wait Time"))

# Gigi's Stuff!!
@app.route('/create/', methods=["GET", "POST"]) 
def create():   
    if request.method == 'GET':
        return render_template(
            'create.html', 
            )
    else:
        # next three lines takes user input from form and stores in variables
        name = request.form['name'] 
        username = request.form['username'] 
        password = request.form['password'] 
        favoriteDH = request.form['diningHall'] 
        classYear = request.form['year'] 

        conn = dbi.connect()

        # next helper function checks to see if username is already in database and prompts user to log in instead 
        if query.username_exists(conn, username): 
            flash('This username already exists. If this is you, please log in. \
                If not, please enter your Wellesley email username.')
            return redirect(url_for('login')) 
        
        # if username doesn't exist, user is added to database and can now log in
        else: 
            query.add_username(conn, name, username, password, favoriteDH, classYear) # used to be add_username, tt, title,  release
            flash('Profile was created successfully! You can now log in')
            return redirect(url_for('login')) 

# allows user to log in
@app.route('/login/', methods=["GET", "POST"])
def login():
    if request.method == 'GET':
        return render_template(
            'create.html'
            )
    # form gets user inputs and stores into variables
    else:
        username = request.form['username'] 
        password = request.form['password'] 
        conn = dbi.connect()
        # helper function checks to make sure username exists in database
        if query.username_exists(conn, username): 
            curs = dbi.dict_cursor(conn)

            # query finds password saved in database to compare with user input
            curs.execute ('''select username, password 
                            from student
                            where username = %s''', [username])
            user = curs.fetchone()
            
            # checks if user input matches password on file
            check_pass = user['password']
            if check_pass  == password:
                flash('Successfully logged in.')
                # print(check_pass, password)
                return redirect(url_for('profile', username=username))
            else:
                flash('Incorrect login. Please try again.')
                return redirect(url_for('login'))

        # if username doesn't exist in database, user is let known
        else: 
            flash('This username does not exist. Please create an account.')
            return redirect(url_for('create')) 

# allows user to see their profile
# how to get actual text instead of values for DH and Classyear 
@app.route('/profile/<username>', methods=['GET','POST'])
def profile(username):
    if request.method == 'GET':
        conn = dbi.connect()
        info = query.get_user_info(conn,username)
        return render_template('profile.html',  
                                info=info,
                                username=username)
    else:
        return render_template('home.html')
        
# should allow user to update profile information. doesn't work yet. ?!?!
@app.route('/update/<username>', methods = ["GET", "POST"])
def update(username):
    conn = dbi.connect()
    info = query.get_user_info(conn, username)
    if request.method == "GET":
        # flash('Profile was updated successfully!')
        return render_template('update.html', 
                                username=username, 
                                info=info)
    else:
        query.update_profile(conn, username, info)
        flash("Successfully updated your profile!")
        return render_template('update.html', 
                                conn=conn,
                                username=username, 
                                info=info)

# temporary solution for catching broken link error
# better way of doing this ?!?!
@app.route('/profile/', methods = ["GET", "POST"])
def profile_error():
    flash("Please log in to see your profile.")
    return render_template('create.html')

# temporary solution for catching broken link error
# better way of doing this ?!?!
@app.route('/update/', methods = ["GET", "POST"])
def username_error():
    flash("Please log in to update your profile.")
    return render_template('create.html')

## Here's the route to entering a feedback form
@app.route('/reviews/<int:fid>',methods=['POST','GET'])
def reviews(fid):
    conn=dbi.connect()
    if request.method=='GET':
        # get the form to display 
        name=feed_queries.search_fid(conn,fid)['name']
        return render_template('feed.html',name=name, fid = fid)
    else:
        # get the input form values from the submitted form
        username=request.form['user']
        #to gigi: how do I link the user here? 
        if len(feed_queries.search_user(conn,username))==0:
            # Because the username is not complete, temp is used for flashing tempoararily 
            # to show available usernames you can possibly input
            temp=[person["username"] for person in feed_queries.temp_user(conn)]
            flash('Username Under Construction:only enter below for usernames:' )
            flash(temp)
            return render_template('feed.html')
        rating=request.form['rating']
        comment=request.form['comment']
        time=datetime.now()
        # stored form info into the database here
        feed_queries.feedback(conn,username,fid,rating,comment,time)
        return redirect(url_for('feed'))

@app.route('/feed/')     
def feed(): #rename review() to feed
    conn=dbi.connect()
    feedbacks= feed_queries.recent_feedback(conn)
    top_rated=feed_queries.food_rating(conn)
    for item in top_rated:
        item['avg']=str(item['avg'])
    return render_template('reviews.html',feedbacks=feedbacks,ranking=top_rated)


@app.route('/addfood/', methods=["GET", "POST"])
def addfood():
    if request.method == 'GET':
        # add a way to dynamically obtain food preferences and allergens
        return render_template('dataentry.html',title='Add Food')
    elif request.method == 'POST':
        conn = dbi.connect()
        food_name = request.form.get('food-name') 
        food_category = request.form.get('food-type')
        food_dhall = request.form.get('food-hall')
        food_preferences = request.form.getlist('preferences')
        food_allergens = request.form.getlist('allergens')
        food_ingredients = request.form.get('food-ingredients')

        # error-handling: if any of the form elements aren't filled out, don't submit the form
        # code elsewhere handles the elements selected by the dropdown

        if len(food_name)==0: 
            flash("Please enter in the name of the food.")
            return render_template(url_for('addfood'), title = 'Add Food')
        if len(food_ingredients) == 0: 
            flash("Please enter in the food's ingredients.")
            return render_template(url_for('addfood'), title = 'Add food')
        if len(food_preferences) == 0 or len(food_allergens) == 0: 
            flash("Please make sure that all boxes in the form are checked.")
            return render_template(url_for('addfood'), title = 'Add food')
        print (['food allergens',food_allergens])

        # entry.handle_empty_values(food_name,food_category,food_dhall,food_preferences,food_allergens,food_ingredients)
        
        test_bool = entry.exists(conn,food_name)
        if test_bool == True: 
            flash("Food already exists in database.")
            return redirect(url_for('addfood')) # should go back to landing page, idk how to do this.
        #inserts food into database
        food_date = today()[0]
        entry.insert_food(conn,food_name,food_date,food_category,food_dhall)
        
        #get food id
        food_id = entry.get_food_id(conn,food_name)
    
        #insert related label into food database: 
        entry.insert_label(conn,food_allergens,food_preferences,food_ingredients,food_id)
        success_message = "Food {fname} inserted".format(fname=food_name)
        flash(success_message)
        return redirect('/')  

@app.route('/delete/', methods=["GET", "POST"]) #change to select and then redirect to delete? 
def delete(): 
    conn = dbi.connect()
    if request.method == "GET": 
        all_foods = entry.get_all_food(conn) 
        all_students = entry.get_all_students(conn)
        # all_comments = entry.get_all_comments(conn) #is there a way to know which user is currently logged in? 

        return render_template('delete.html', title = 'Delete Food', allfoods=all_foods, students=all_students)
        #later, get a dynamic list of usernames
    if request.method == "POST":
        #flesh this out a little bit–using info that the user selected, delete food item.
        #also, only allow delete to happen if the "right" username is selected 
        print(request.form)
        student_str = request.form.get('student-name') 
        food_id = request.form.get('food-dlt') 
        print([student_str,food_id])
        if student_str == 'none' or food_id == 'none': 
            flash('Please make sure you have selected a username and food item to delete.')
            return redirect(url_for('delete'), title = 'Delete Food')
        elif student_str not in ['fx1','ggabeau','lteffera','sclark4','scott']: 
            flash('Sorry, but you are not authorized to delete food items from the database.')
            return redirect('/')
        food_name = entry.get_food(conn,food_id)

        entry.delete_comments(conn,food_id) #haven't checked (don't want to delete anything that already exists in db)
        entry.delete_labels(conn,food_id)
        entry.delete_food(conn,food_id)
        flash('{fname} was successfully deleted from the database.'.format(fname=food_name))
        return redirect('/')



    
@app.before_first_request
def init_db():
    dbi.cache_cnf()
    dbi.use('foodie_db')  

if __name__ == '__main__':
    import sys, os
    if len(sys.argv) > 1:
        # arg, if any, is the desired port number
        port = int(sys.argv[1])
        assert(port>1024)
    else:
        # port = os.getuid()
        port = 7739
    app.debug = True
    app.run('0.0.0.0',port)
