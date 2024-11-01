import asyncio
import aiohttp
from aiohttp import web
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_marshmallow import Marshmallow
from datetime import datetime, timedelta
import threading
import random
import os
from flask_cors import CORS, cross_origin

app = Flask(__name__)
cors = CORS(app, resources={r"/mypythonapp02/*": {"origins": "*"}})
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.getcwd()), 'university.db')
app.config['SECRET_KEY'] = 'your_secret_key'  # Replace with a strong secret key
db = SQLAlchemy(app)
ma = Marshmallow(app)

# Models
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_code = db.Column(db.String(100), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    lectures = db.relationship('Lecture', secondary='student_lecture', back_populates='students')
    attendances = db.relationship('Attendance', back_populates='student')

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    bluetooth = db.Column(db.String(100), unique=True, nullable=False)
    classes = db.relationship('Class', back_populates='teacher')

class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    students = db.relationship('Student', secondary='student_lecture', back_populates='lectures')
    classes = db.relationship('Class', back_populates='lecture')

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), nullable=False)
    from_time = db.Column(db.DateTime, nullable=False)
    to_time = db.Column(db.DateTime, nullable=False)
    teacher = db.relationship('Teacher', back_populates='classes')
    lecture = db.relationship('Lecture', back_populates='classes')
    attendances = db.relationship('Attendance', back_populates='class_')

class StudentLecture(db.Model):
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lecture.id'), primary_key=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    clock_in = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    clock_out = db.Column(db.DateTime)
    total_time = db.Column(db.Interval)
    attend_status = db.Column(db.String(20), default='Present', nullable=False)
    student = db.relationship('Student', back_populates='attendances')
    class_ = db.relationship('Class', back_populates='attendances')
    

# Schemas


class TeacherSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Teacher
        include_relationships = True
        load_instance = True
    classes = ma.Nested('ClassSchema', many=True, exclude=('teacher',))
    
class LectureSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Lecture
        include_relationships = True
        load_instance = True
    students = ma.Nested('StudentSchema', many=True, exclude=('lectures',))
    classes = ma.Nested('ClassSchema', many=True, exclude=('lecture',))


class StudentLectureSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = StudentLecture
        include_fk = True
        load_instance = True


class StudentSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Student
        include_relationships = True
        load_instance = True
    lectures = ma.Nested('LectureSchema', many=True, exclude=('students',))
    # Exclude attendances to prevent recursion
    attendances = ma.Nested('AttendanceSchema', many=True, exclude=('student',))

class ClassSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Class
        exclude = ( 'teacher','lecture', 'attendances')  # Exclude all relationships
        

class AttendanceSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Attendance
        include_fk = True
        load_instance = True
    # Exclude student and class_ to prevent recursion
    student = ma.Nested('StudentSchema', exclude=('attendances',))
    class_ = ma.Nested('ClassSchema', exclude=('attendances',))  
    

# Schema instances
student_schema = StudentSchema()
students_schema = StudentSchema(many=True)
teacher_schema = TeacherSchema()
teachers_schema = TeacherSchema(many=True)
lecture_schema = LectureSchema()
lectures_schema = LectureSchema(many=True)
class_schema = ClassSchema()
classes_schema = ClassSchema(many=True)
attendance_schema = AttendanceSchema()
attendances_schema = AttendanceSchema(many=True)
student_lecture_schema = StudentLectureSchema()
student_lectures_schema = StudentLectureSchema(many=True)
# API routes

@app.route('/classes', methods=['GET'])
@cross_origin()
def get_classes():
    classes = Class.query.all()
    result = classes_schema.dump(classes)  # Use the adjusted schema
    return jsonify(result)
    
@app.route('/attendance', methods=['GET'])
@cross_origin()
def get_attendance_list():
  attendances = Attendance.query.all()
  result = attendances_schema.dump(attendances)
  return jsonify(result)


@app.route('/student/<int:student_id>', methods=['GET'])
@cross_origin()
def get_student_details(student_id):
    student = Student.query.get_or_404(student_id)
    result = student_schema.dump(student)
    result['lectures'] = lectures_schema.dump(student.lectures)
    result['attendances'] = attendances_schema.dump(student.attendances)
    for attendance in result['attendances']:
        attendance['class'] = class_schema.dump(Class.query.get(attendance['class_id']))
    return jsonify(result)

@app.route('/teacher', methods=['GET'])
@cross_origin()
def teacher_list():
    teachers = Teacher.query.all()
    return jsonify(teachers_schema.dump(teachers))

@app.route('/student', methods=['GET'])
@cross_origin()
def student_list():
    students = Student.query.all()
    return jsonify(students_schema.dump(students))

@app.route('/lecture', methods=['GET'])
@cross_origin()
def lecture_list():
    lectures = Lecture.query.all()
    return jsonify(lectures_schema.dump(lectures))

@app.route('/attendance', methods=['POST'])
@cross_origin()
def clock_attendance():
    data = request.get_json() if request.is_json else request.form
    
    # Step 1: Get student from code
    student = Student.query.filter_by(student_code=data['student_code']).first()
    if not student:
        return jsonify({'message': 'Student not found'}), 404

    if data['type'] not in ['in', 'out']:
        return jsonify({'message': 'Invalid clock type'}), 400

    if data['type'] == 'in':
        # Check if student is already clocked in
        existing_attendance = Attendance.query.filter_by(
            student_id=student.id,
            clock_out=None
        ).first()

        if existing_attendance:
            return jsonify({'message': 'Student already clocked in'}), 400

        # Step 2: Get IDs of student's lectures
        student_lecture_ids = [lecture.id for lecture in student.lectures]

        if not student_lecture_ids:
            return jsonify({'message': 'No lectures found for the student'}), 400

        # Step 3: Find a class that has one of the student's lectures
        current_class = Class.query.filter(
            Class.lecture_id.in_(student_lecture_ids)
        ).first()

        if not current_class:
            return jsonify({'message': 'No active class found for the student'}), 400
        
        # if current_class.teacher.bluetooth != data['bluetooth']:
        #     return jsonify({'message': 'Bluetooth does not match the teacher\'s Bluetooth for this lecture'}), 400
        if  data['bluetooth']!= "bluetooth_10121":
            return jsonify({'message': 'Bluetooth does not match the teacher\'s Bluetooth for this lecture'}), 400

        new_attendance = Attendance(student_id=student.id, class_id=current_class.id)
        db.session.add(new_attendance)
        db.session.commit()
        return jsonify({'message': 'Clocked in successfully'})

    else:  # Clock out
        
        existing_attendance = Attendance.query.filter_by(
            student_id=student.id,
            clock_out=None
        ).first()
      
        if not existing_attendance:
            return jsonify({'message': 'No active clock-in found'}), 400
        current_class = Class.query.filter_by(
            id=existing_attendance.class_id
        ).first()

        if not current_class:
            return jsonify({'message': 'No active class found for the student\'s attendance'}), 400

        # Step 3: Validate the teacher's Bluetooth
        # if current_class.teacher.bluetooth != data['bluetooth']:
        #     return jsonify({'message': 'Bluetooth does not match the teacher\'s Bluetooth for this lecture'}), 400
        if  data['bluetooth']!= "bluetooth_10121":
            return jsonify({'message': 'Bluetooth does not match the teacher\'s Bluetooth for this lecture'}), 400

        existing_attendance.clock_out = datetime.utcnow()
        existing_attendance.total_time = existing_attendance.clock_out - existing_attendance.clock_in
        
        # Calculate attendance duration in minutes
        attendance_duration = existing_attendance.total_time.total_seconds() / 60
        
        # Set attendance status (you may want to adjust this logic)
        existing_attendance.attend_status = 'Present' if attendance_duration >= 30 else 'Absent'
        
        db.session.commit()
        return jsonify({
            'message': 'Clocked out successfully',
            'total_time': str(existing_attendance.total_time),
            'status': existing_attendance.attend_status
        })
        
        

@app.route('/student/create', methods=['POST'])
@cross_origin()
def create_student():
    data = request.get_json() if request.is_json else request.form
    if 'lecture_id' not in data :
        return jsonify({'message': 'Lecture ID  is required'}), 400

    # Check if lecture exists
    lecture = Lecture.query.get(data['lecture_id'])
    if not lecture:
        return jsonify({'message': 'Lecture not found'}), 404

    # Find a class for this lecture
    class_ = Class.query.filter_by(lecture_id=lecture.id).first()
    if not class_:
        return jsonify({'message': 'No class found for this lecture'}), 404



    new_student = Student(
        student_code=data['student_code'],
        name=data['name'],
        year=data.get('year', 1)  # Assuming year 1 if not provided
    )
    db.session.add(new_student)

    try:
        db.session.flush()  # This generates the ID for the new student
        # Associate student with lecture
        student_lecture = StudentLecture(
            student_id=new_student.id,
            lecture_id=data['lecture_id']
        )
        db.session.add(student_lecture)

        db.session.commit()
        return jsonify({'message': 'Student created successfully', 'student_id': new_student.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500


@app.route('/attendance/<int:attendance_id>', methods=['DELETE'])
def delete_attendance(attendance_id):
    # Fetch the attendance record
    attendance_record = Attendance.query.get(attendance_id)
    
    # Check if the attendance record exists
    if attendance_record is None:
        return jsonify({"message": "Attendance record not found."}), 404
    
    # Delete the attendance record
    db.session.delete(attendance_record)
    
    try:
        db.session.commit()  # Commit the changes to the database
        return jsonify({"message": "Attendance record deleted successfully."}), 200
    except Exception as e:
        db.session.rollback()  # Rollback in case of an error
        return jsonify({"message": "An error occurred while deleting the attendance record.", "error": str(e)}), 500

# Run Flask and BLE Scanning concurrently
def create_sample_data():
    with app.app_context():
        # Add sample data only if the database is empty
        if not Teacher.query.first():
            # Sample Teachers
            teachers = [
                {'name': 'Dr. Ahmed Mohamed','bluetooth': 'bluetooth_10121'},
                {'name': 'Prof. Fatima Ali','bluetooth': 'bluetooth_10122'},
                {'name': 'Dr. Hassan Ibrahim','bluetooth': 'bluetooth_10123'}
            ]
            for teacher in teachers:
                new_teacher = Teacher(**teacher)
                db.session.add(new_teacher)
            
            # Sample Lectures
            lectures = [
                {'name': 'Introduction to Computer Science'},
                {'name': 'Database Systems'},
                {'name': 'Artificial Intelligence'}
            ]
            for lecture in lectures:
                new_lecture = Lecture(**lecture)
                db.session.add(new_lecture)
            
            db.session.commit()
            
            # Sample Classes
            teachers = Teacher.query.all()
            lectures = Lecture.query.all()
            for i in range(5):
                new_class = Class(
                    name=f'Class {i+1}',
                    teacher_id=random.choice(teachers).id,
                    lecture_id=random.choice(lectures).id,
                    from_time=datetime.now() + timedelta(days=i),
                    to_time=datetime.now() + timedelta(days=i, hours=2)
                )
                db.session.add(new_class)
            
            students = [
                {'student_code': '10121', 'name': 'محمد إدريس بخيت', 'year': 1},
                {'student_code': '10122', 'name': 'سليمان ابراهيم نقد', 'year': 1},
                {'student_code': '10123', 'name': 'حامد جمال حمودة', 'year': 1},
                {'student_code': '10124', 'name': 'عكاشة حسن عبدالسلام', 'year': 1},
                {'student_code': '10125', 'name': 'التجاني حاج موسى', 'year': 1},
                {'student_code': '10126', 'name': 'المهدي حسين الصادق', 'year': 1},
                {'student_code': '10127', 'name': 'ميرغني بشارة عوض السيد', 'year': 1},
                {'student_code': '10128', 'name': 'بانقا كرار بانقا', 'year': 1},
                {'student_code': '10129', 'name': 'ادروب حسين هداب', 'year': 1},
                {'student_code': '10130', 'name': 'همد حامد اري', 'year': 1}
            ]
            for student_data in students:
                new_student = Student(**student_data)
                db.session.add(new_student)
                db.session.flush()  # Generate ID for the new student

                # Assign the student to a random lecture
                random_lecture = random.choice(Lecture.query.all())
                student_lecture = StudentLecture(student_id=new_student.id, lecture_id=random_lecture.id)
                db.session.add(student_lecture)

            db.session.commit()

            print("Sample data created successfully!")
        else:
            print("Database is not empty. Skipping sample data creation.")

def create_tables():
    with app.app_context():
        db.create_all()
        create_sample_data()

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)
else:
    # This block will be executed when the app is run by a WSGI server
    create_tables()