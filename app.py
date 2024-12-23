from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure database
if os.environ.get('DATABASE_URL'):
    # Use PostgreSQL for production
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # Use SQLite for development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///surveys.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    surveyor_name = db.Column(db.String(100), nullable=False)
    submission_time = db.Column(db.DateTime, nullable=False)
    note = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

# Create tables
with app.app_context():
    try:
        db.drop_all()
        db.create_all()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/leaderboard')
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/submit_survey', methods=['POST'])
def submit_survey():
    try:
        if not request.is_json:
            logger.error("Request is not JSON")
            return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

        data = request.get_json()
        logger.debug(f"Received data: {data}")

        if not data.get('name'):
            return jsonify({'status': 'error', 'message': 'Name is required'}), 400

        if not data.get('time'):
            return jsonify({'status': 'error', 'message': 'Time is required'}), 400

        # Parse the time string
        try:
            submission_time = datetime.strptime(data['time'], '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            try:
                submission_time = datetime.strptime(data['time'], '%Y-%m-%dT%H:%M:%SZ')
            except ValueError as e:
                logger.error(f"Error parsing time: {str(e)}")
                return jsonify({'status': 'error', 'message': 'Invalid time format'}), 400

        submission = Submission(
            surveyor_name=data['name'],
            submission_time=submission_time,
            note=data.get('note', ''),
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )
        
        logger.debug(f"Creating submission: {submission.surveyor_name}, {submission.submission_time}, Location: ({submission.latitude}, {submission.longitude})")
        db.session.add(submission)
        db.session.commit()
        logger.info("Submission saved successfully")
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error in submit_survey: {str(e)}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_submissions')
def get_submissions():
    try:
        date_filter = request.args.get('date')
        query = Submission.query

        if date_filter:
            # Convert date string to datetime
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
            next_date = filter_date + timedelta(days=1)
            query = query.filter(
                Submission.submission_time >= filter_date,
                Submission.submission_time < next_date
            )

        submissions = query.order_by(Submission.submission_time.desc()).all()
        return jsonify([{
            'name': sub.surveyor_name,
            'time': sub.submission_time.strftime('%Y-%m-%d %H:%M:%S'),
            'note': sub.note,
            'latitude': sub.latitude,
            'longitude': sub.longitude
        } for sub in submissions])
    except Exception as e:
        logger.error(f"Error in get_submissions: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_stats')
def get_stats():
    try:
        view_type = request.args.get('view', 'total')  # 'total' or 'daily'
        total_target = 7000
        daily_quota = total_target // 4

        if view_type == 'daily':
            # Get today's submissions
            today = datetime.utcnow().date()
            tomorrow = today + timedelta(days=1)
            total_submissions = Submission.query.filter(
                Submission.submission_time >= today,
                Submission.submission_time < tomorrow
            ).count()
            target = daily_quota
        else:
            # Get all submissions
            total_submissions = Submission.query.count()
            target = total_target

        # Get submissions per surveyor for leaderboard with percentages
        leaderboard_data = db.session.query(
            Submission.surveyor_name,
            db.func.count(Submission.id).label('count')
        ).group_by(Submission.surveyor_name).order_by(db.text('count DESC')).all()
        
        # Calculate percentages
        leaderboard = []
        for name, count in leaderboard_data:
            percentage = (count / total_submissions * 100) if total_submissions > 0 else 0
            leaderboard.append({
                'name': name,
                'count': count,
                'percentage': round(percentage, 1)
            })
        
        return jsonify({
            'total_submissions': total_submissions,
            'target': target,
            'daily_quota': daily_quota,
            'progress_percentage': (total_submissions / target) * 100,
            'view_type': view_type,
            'leaderboard': leaderboard
        })
    except Exception as e:
        logger.error(f"Error in get_stats: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
