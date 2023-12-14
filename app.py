from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.secret_key = 'many random bytes'
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'votingsystem'

mysql = MySQL(app)

class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)
"""
@login_manager.user_loader
def load_user(user_id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM admin WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()

    if user:
        # Assuming 'id' and 'name' are the column names in your 'admin' table
        return User(user[0], user[3])
    return None
    """

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))



@app.route('/', methods=['GET', 'POST'])
def index():
     # Check for max_vote exceeded
    error_message = None
    success_message = None
    selected_candidates_details = []

    # Simulating database query
    cur = mysql.connection.cursor()
    cur.execute("SELECT candidates.*, positions.description, positions.max_vote FROM candidates INNER JOIN positions ON candidates.position_id = positions.id ORDER BY positions.priority")
    candidates = cur.fetchall()
    cur.close()

    cur = mysql.connection.cursor()
    cur.execute("SELECT e_title FROM election_title LIMIT 1")
    election_title = cur.fetchone()[0] if cur.rowcount > 0 else "Default Election Title"
    cur.close()

    # Organize candidates by positions
    candidates_by_positions = {}
    for candidate in candidates:
        position_id = candidate[1]
        if position_id not in candidates_by_positions:
            candidates_by_positions[position_id] = {"candidates": [], "max_vote": candidate[6]}

        candidates_by_positions[position_id]["candidates"].append({
            "id": candidate[0],
            "name": candidate[2].upper(),
            "position_id": position_id,
            "position_name": candidate[5],
            "background": candidate[3],
            "projects": candidate[4],
        })

    if request.method == 'POST':
        voter_id = None
        voter_id = request.form['voter_id']

        # Check if the voter_id already exists in the database
        cur = mysql.connection.cursor()
        cur.execute("SELECT COUNT(*) FROM voters WHERE voters_id = %s", (int(voter_id),))
        count = cur.fetchone()[0]
        cur.close()

        if count > 0:
            # If the voter_id already exists, set an error_message
            error_message = f"Voter with ID {int(voter_id)} has already voted."
        else:
            # If the voter_id doesn't exist, proceed with the insertion
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO voters (voters_id) VALUES (%s)", (int(voter_id),))
            mysql.connection.commit()
            cur.close()

            for position_id, position_data in candidates_by_positions.items():
                selected_candidates = len(request.form.getlist(f"position_{position_id}_options"))
                selected_candidates_ids = request.form.getlist(f"position_{position_id}_options")
                max_vote = position_data["max_vote"]
                if selected_candidates > max_vote:
                    error_message = f"You can only select up to {max_vote} candidates for the position of {position_data['candidates'][0]['position_name']}."
                else:
                # Loop through selected candidate IDs and add details to the list
                    success_message = f"Your vote has been submitted."
                    for candidate_id in selected_candidates_ids:
                        candidate_details = {
                            "position_name": position_data["candidates"][0]["position_name"],
                            "candidate_name": next(
                                (candidate["name"] for candidate in position_data["candidates"] if candidate["id"] == int(candidate_id)),
                                None
                            ),
                        }
                        selected_candidates_details.append(candidate_details)

                        # Insert the selected candidate ID into the total_vote table
                        cur = mysql.connection.cursor()
                        cur.execute("INSERT INTO total_votes (candidates_id) VALUES (%s)", (int(candidate_id),))
                        mysql.connection.commit()
                        cur.close()

    return render_template('index.html', candidates_by_positions=candidates_by_positions, selected_candidates_details=selected_candidates_details, error_message=error_message, election_title=election_title, success_message=success_message)

@app.route('/admin', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM admin WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()

        if user and bcrypt.check_password_hash(user[2], password):
            user_id = user[0]
            user_object = User(user_id)
            login_user(user_object)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'error')
            return redirect(url_for('login'))

    return render_template('/login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    pos = mysql.connection.cursor()
    pos.execute("SELECT COUNT(id) FROM positions")
    position_count = pos.fetchone()[0]
    pos.close()

    can = mysql.connection.cursor()
    can.execute("SELECT COUNT(id) FROM candidates")
    candidate_count = can.fetchone()[0]
    pos.close()

    voters = mysql.connection.cursor()
    voters.execute("SELECT COUNT(id) FROM voters")
    voters_count = voters.fetchone()[0]
    pos.close()

    cur = mysql.connection.cursor()
    cur.execute("SELECT positions.description, COUNT(candidates.position_id) FROM candidates INNER JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.position_id")
    votetally = cur.fetchall()
    cur.close()
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT candidates.id AS candidate_id, candidates.fullname AS candidate_fullname, positions.description AS position_description, COUNT(total_votes.candidates_id) AS total_votes FROM candidates LEFT JOIN total_votes ON candidates.id = total_votes.candidates_id LEFT JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.id, candidates.fullname, positions.description ORDER BY positions.priority, total_votes DESC, candidates.id;")
    candidates = cur.fetchall()
    cur.close()

    title = mysql.connection.cursor()
    title.execute("SELECT * FROM election_title")
    e_title = title.fetchall()
    title.close()

    return render_template('dashboard.html', position_count=position_count, candidate_count=candidate_count, voters_count=voters_count, votetally=votetally, candidates=candidates, e_title=e_title)

@app.route('/updatetitle', methods=['POST', 'GET'])
@login_required
def updatetitle():
    if request.method == 'POST':
        id_data = request.form['id']
        TITLE = request.form['e_titles']
        cur = mysql.connection.cursor()
        cur.execute("UPDATE election_title SET e_title=%s WHERE id=%s", (TITLE  , id_data))
        mysql.connection.commit()

    return redirect(url_for('dashboard'))


@app.route('/votes')
@login_required
def votes():

    votes = mysql.connection.cursor()
    votes.execute("SELECT * FROM voters")
    voters = votes.fetchall()
    votes.close()

    reset_voters = session.pop('candidatetally', None)

    return render_template('votes.html', voters=voters, reset_voters=reset_voters)

@app.route('/pdf')
def generate_pdf():
    # Fetch data from the "voters" table
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT candidates.id AS candidate_id, candidates.fullname AS candidate_fullname, positions.description AS position_description, COUNT(total_votes.candidates_id) AS total_votes, positions.priority FROM candidates LEFT JOIN total_votes ON candidates.id = total_votes.candidates_id LEFT JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.id, candidates.fullname, positions.description ORDER BY positions.priority, total_votes DESC, candidates.id")
    voters = cursor.fetchall()
    cursor.close()

    # Create a BytesIO buffer for the PDF
    pdf_buffer = BytesIO()

    # Create the PDF document
    pdf = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    data = [["Position", "Name", "Total Votes"]]
    style = getSampleStyleSheet()
    # Add data to the PDF
    # Create a list to preserve the order of positions
    
    # Sort positions based on priority
    positions_order = sorted(set(voter[2] for voter in voters), key=lambda x: [v for v in voters if v[2] == x][0][4])

    for position in positions_order:
        # Add a title for each position
        position_title = Paragraph(position, style["Heading2"])
        data.append([position_title, '', ''])  # Empty row as a separator
        position_data = [[voter[2], voter[1], voter[3]] for voter in voters if voter[2] == position]
        data.extend(position_data)


        # Add title to the PDF
        title = "Voting Results"
        pdf_title_style = ParagraphStyle(
            "centered_title",
            parent=style["Heading1"],
            alignment=1  # 0=left, 1=center, 2=right
        )
        pdf_title = Paragraph(title, pdf_title_style)

        # Create table
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),  # Header background color
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),  # Header text color
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center alignment for all cells
            ('GRID', (0, 0), (-1, -1), 1, colors.black)  # Border around cells
        ]))

        # Build PDF
        elements = [pdf_title, table]
        pdf.build(elements)

        # Move the buffer's position to the beginning
        pdf_buffer.seek(0)

        # Create a Flask response with the PDF
        response = make_response(pdf_buffer.read())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=voting_results.pdf'

    return response

@app.route('/deleterecords')
@login_required
def deleterecords():

    cur = mysql.connection.cursor()
    cur.execute("TRUNCATE TABLE voters")
    mysql.connection.commit()

    session['candidatetally'] = "Delete voters record Successfully"

    return redirect(url_for('votes'))

@app.route('/candidatetally')
@login_required
def candidatetally():

    cur1 = mysql.connection.cursor()
    cur1.execute("SELECT max(id) FROM total_votes")
    max_id = cur1.fetchall()
    cur1.close()

    if max_id == 0:
        cur = mysql.connection.cursor()
        cur.execute("SELECT candidates.id AS candidate_id, candidates.fullname AS candidate_fullname, positions.description AS position_description, COUNT(total_votes.candidates_id) AS total_votes FROM candidates LEFT JOIN total_votes ON candidates.id = total_votes.candidates_id LEFT JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.id, candidates.fullname, positions.description ORDER BY positions.priority, total_votes DESC;")
        votetally = cur.fetchall()
        cur.close()
    else:
        cur = mysql.connection.cursor()
        cur.execute("SELECT candidates.id AS candidate_id, candidates.fullname AS candidate_fullname, positions.description AS position_description, COUNT(total_votes.candidates_id) AS total_votes FROM candidates LEFT JOIN total_votes ON candidates.id = total_votes.candidates_id LEFT JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.id, candidates.fullname, positions.description ORDER BY positions.priority, total_votes DESC, candidates.id")
        votetally = cur.fetchall()
        cur.close()

    reset_vote = session.pop('candidatetally', None)

    return render_template('votess.html', votetally=votetally, reset_vote=reset_vote)

@app.route('/resetvotes')
@login_required
def resetvotes():

    cur = mysql.connection.cursor()
    cur.execute("TRUNCATE TABLE total_votes")
    mysql.connection.commit()

    session['candidatetally'] = "Reset votes Successfully"

    return redirect('candidatetally')

@app.route('/candidates')
@login_required
def candidates():

    cur = mysql.connection.cursor()
    cur.execute("SELECT candidates.*, positions.*, COUNT(total_votes.candidates_id) AS total_votes FROM candidates LEFT JOIN total_votes ON candidates.id = total_votes.candidates_id LEFT JOIN positions ON candidates.position_id = positions.id GROUP BY candidates.id, candidates.fullname, positions.description ORDER BY positions.priority, candidates.id;")
    candidates = cur.fetchall()
    cur.close()

    cur1 = mysql.connection.cursor()
    cur1.execute("SELECT positions.id, positions.description FROM positions")
    position = cur1.fetchall()
    cur1.close()

    return render_template('candidates.html', candidates=candidates, position=position)

@app.route('/insert', methods=['POST'])
@login_required
def insert():
    if request.method == "POST":
        cur = mysql.connection.cursor()
        cur.execute("SELECT MAX(id) FROM candidates")
        max_id = cur.fetchone()[0]
        cur.close()

        if max_id is None:
            next_id = 1
        else:
            next_id = int(max_id) + 1
    
        name = request.form['name']
        position = request.form['position_id']
        background = request.form['background']
        projects = request.form['projects']
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO candidates (id, fullname, position_id, background, projects) VALUES (%s, %s, %s, %s, %s)", (next_id, name, position, background, projects))
        mysql.connection.commit()
        flash("Data Inserted Successfully")
        return redirect(url_for('candidates'))

@app.route('/update', methods=['POST', 'GET'])
@login_required
def update():

    if request.method == 'POST':
        id_data = request.form['id']
        name = request.form['name']
        position_id = request.form['position_id']
        background = request.form['background']
        projects = request.form['projects']
        cur = mysql.connection.cursor()
        cur.execute("""
               UPDATE candidates
               SET fullname=%s, position_id=%s, background=%s, projects=%s
               WHERE id=%s
            """, (name, position_id, background, projects, id_data))
        flash("Data Updated Successfully")
        mysql.connection.commit()
        return redirect(url_for('candidates'))
    
@app.route('/delete/<string:id_data>', methods=['GET'])
@login_required
def delete(id_data):
    flash("Record Has Been Deleted Successfully")
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM candidates WHERE id=%s", (id_data,))
    mysql.connection.commit()
    return redirect(url_for('candidates'))

@app.route('/newposition')
@login_required
def newposition():

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM positions")
    positions = cur.fetchall()
    cur.close()

    newposition_message = session.pop('newposition', None)

    return render_template('newposition.html', positions=positions, newposition_message=newposition_message)

@app.route('/insertposition', methods=['POST', 'GET'])
@login_required
def insertposition():

    if request.method == "POST":
        cur = mysql.connection.cursor()
        cur.execute("SELECT MAX(id) FROM positions")
        max_id = cur.fetchone()[0]
        cur.close()

        if max_id is None:
            id = 1
        else:
            id = int(max_id) + 1

        cur = mysql.connection.cursor()
        cur.execute("SELECT MAX(priority) FROM positions")
        max_priority = cur.fetchone()[0]
        cur.close()

        if max_priority is None:
            priority = 1
        else:
            priority = int(max_priority) + 1
    
        description = request.form['description']
        max_vote = request.form['max_vote']
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO positions (id, description, max_vote, priority) VALUES (%s, %s, %s, %s)", (id, description, max_vote, priority))
        mysql.connection.commit()

        session['newposition'] = "Data Inserted Successfully"
    
    return redirect(url_for('newposition'))

@app.route('/updateposition', methods=['POST', 'GET'])
@login_required
def updateposition():

    if request.method == 'POST':
        id_data = request.form['id']
        description = request.form['description']
        max_vote = request.form['max_vote']
        priority = request.form['priority']
        cur = mysql.connection.cursor()
        cur.execute("""
               UPDATE positions
               SET description=%s, max_vote=%s, priority=%s
               WHERE id=%s
            """, (description, max_vote, priority, id_data))
        session['newposition'] = "Data Updated Successfully"
        mysql.connection.commit()
        return redirect(url_for('newposition', newposition=newposition))
    
@app.route('/deleteposition/<string:id_data>', methods=['GET'])
@login_required
def deleteposition(id_data):
    session['newposition'] = "Record Has Been Deleted Successfully"
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM positions WHERE id=%s", (id_data,))
    mysql.connection.commit()
    return redirect(url_for('newposition'))



if __name__ == '__main__':
    app.run(debug=True)
