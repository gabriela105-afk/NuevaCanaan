-- Esquema PostgreSQL de la plataforma Nueva Canaán
-- Generado automáticamente desde app/models.py
-- Pegar en Supabase → SQL Editor → New query → Run

CREATE TABLE contact_messages (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	email VARCHAR(180), 
	phone VARCHAR(40), 
	subject VARCHAR(160) NOT NULL, 
	body TEXT NOT NULL, 
	ip_address VARCHAR(60), 
	is_read BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_contact_messages_created_at ON contact_messages (created_at);

CREATE TABLE courses (
	id SERIAL NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	level VARCHAR(60), 
	parallel VARCHAR(10) NOT NULL, 
	academic_year INTEGER NOT NULL, 
	description VARCHAR(200), 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_courses_name_parallel_year UNIQUE (name, parallel, academic_year)
);

CREATE TABLE institution_settings (
	key VARCHAR(60) NOT NULL, 
	value TEXT, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE students (
	id SERIAL NOT NULL, 
	code VARCHAR(30) NOT NULL, 
	first_name VARCHAR(80) NOT NULL, 
	last_name VARCHAR(80) NOT NULL, 
	birth_date DATE, 
	gender VARCHAR(20), 
	notes TEXT, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_students_code ON students (code);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	email VARCHAR(180) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(160) NOT NULL, 
	phone VARCHAR(40), 
	role VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	failed_login_attempts INTEGER NOT NULL, 
	locked_until TIMESTAMP WITHOUT TIME ZONE, 
	last_login_at TIMESTAMP WITHOUT TIME ZONE, 
	last_login_ip VARCHAR(60), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('admin','direction','teacher','parent','student'))
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE INDEX ix_users_role ON users (role);

CREATE TABLE announcements (
	id SERIAL NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	summary VARCHAR(300), 
	body TEXT NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	priority VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	audience VARCHAR(20) NOT NULL, 
	target_role VARCHAR(20), 
	is_pinned BOOLEAN NOT NULL, 
	published_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at DATE, 
	attachment_path VARCHAR(255), 
	attachment_name VARCHAR(255), 
	attachment_mime VARCHAR(120), 
	attachment_size INTEGER, 
	author_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_announcement_status CHECK (status IN ('draft','published','archived')), 
	CONSTRAINT ck_announcement_priority CHECK (priority IN ('baja','normal','alta','urgente')), 
	CONSTRAINT ck_announcement_audience CHECK (audience IN ('public','internal')), 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_announcements_category ON announcements (category);

CREATE INDEX ix_announcements_published_at ON announcements (published_at);

CREATE INDEX ix_announcements_status ON announcements (status);

CREATE INDEX ix_announcements_status_publication ON announcements (status, published_at);

CREATE TABLE attendance (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	date DATE NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	notes VARCHAR(200), 
	recorded_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_attendance_student_course_date UNIQUE (student_id, course_id, date), 
	CONSTRAINT ck_attendance_status CHECK (status IN ('presente','ausente','tarde','justificado')), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE, 
	FOREIGN KEY(recorded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_attendance_date ON attendance (date);

CREATE INDEX ix_attendance_student_id ON attendance (student_id);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	actor_id INTEGER, 
	actor_name VARCHAR(160), 
	action VARCHAR(80) NOT NULL, 
	entity VARCHAR(60), 
	entity_id INTEGER, 
	details VARCHAR(400), 
	ip_address VARCHAR(60), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE TABLE events (
	id SERIAL NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	description TEXT, 
	start_date DATE NOT NULL, 
	start_time TIME WITHOUT TIME ZONE, 
	end_date DATE, 
	location VARCHAR(160), 
	category VARCHAR(30) NOT NULL, 
	audience VARCHAR(20) NOT NULL, 
	target_role VARCHAR(20), 
	course_id INTEGER, 
	created_by INTEGER, 
	is_cancelled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_event_audience CHECK (audience IN ('public','internal')), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_events_category ON events (category);

CREATE INDEX ix_events_date ON events (start_date);

CREATE TABLE messages (
	id SERIAL NOT NULL, 
	sender_id INTEGER NOT NULL, 
	recipient_id INTEGER NOT NULL, 
	subject VARCHAR(160) NOT NULL, 
	body TEXT NOT NULL, 
	parent_id INTEGER, 
	read_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(recipient_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(parent_id) REFERENCES messages (id) ON DELETE SET NULL
);

CREATE INDEX ix_messages_recipient_read ON messages (recipient_id, read_at);

CREATE TABLE news_posts (
	id SERIAL NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	summary VARCHAR(300), 
	body TEXT NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	is_pinned BOOLEAN NOT NULL, 
	allow_comments BOOLEAN NOT NULL, 
	published_at TIMESTAMP WITHOUT TIME ZONE, 
	author_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_news_post_status CHECK (status IN ('draft','published','archived')), 
	FOREIGN KEY(author_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_news_posts_category ON news_posts (category);

CREATE INDEX ix_news_posts_published_at ON news_posts (published_at);

CREATE INDEX ix_news_posts_status ON news_posts (status);

CREATE INDEX ix_news_posts_status_publication ON news_posts (status, published_at);

CREATE TABLE notifications (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	body VARCHAR(400), 
	link VARCHAR(255), 
	category VARCHAR(40), 
	read_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_notifications_user_read ON notifications (user_id, read_at);

CREATE TABLE parents (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	relationship VARCHAR(40), 
	occupation VARCHAR(120), 
	address VARCHAR(200), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE student_enrollments (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	academic_year INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_enrollment_student_course UNIQUE (student_id, course_id, academic_year), 
	CONSTRAINT ck_enrollment_status CHECK (status IN ('activo','retirado','egresado')), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE INDEX ix_student_enrollments_course_id ON student_enrollments (course_id);

CREATE INDEX ix_student_enrollments_student_id ON student_enrollments (student_id);

CREATE TABLE teachers (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	employee_code VARCHAR(30), 
	specialty VARCHAR(120), 
	hire_date DATE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	UNIQUE (employee_code)
);

CREATE TABLE announcement_recipients (
	id SERIAL NOT NULL, 
	announcement_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_announcement_course UNIQUE (announcement_id, course_id), 
	FOREIGN KEY(announcement_id) REFERENCES announcements (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE TABLE assignments (
	id SERIAL NOT NULL, 
	course_id INTEGER NOT NULL, 
	teacher_id INTEGER, 
	title VARCHAR(180) NOT NULL, 
	description TEXT, 
	kind VARCHAR(20) NOT NULL, 
	subject VARCHAR(80), 
	due_date DATE, 
	max_score FLOAT, 
	is_published BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_assignment_kind CHECK (kind IN ('tarea','evaluacion','actividad')), 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE, 
	FOREIGN KEY(teacher_id) REFERENCES teachers (id) ON DELETE SET NULL
);

CREATE INDEX ix_assignments_course_due ON assignments (course_id, due_date);

CREATE TABLE course_assignments (
	id SERIAL NOT NULL, 
	teacher_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	subject VARCHAR(80) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_course_assignment UNIQUE (teacher_id, course_id, subject), 
	FOREIGN KEY(teacher_id) REFERENCES teachers (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE
);

CREATE TABLE news_comments (
	id SERIAL NOT NULL, 
	post_id INTEGER NOT NULL, 
	author_name VARCHAR(80) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	visitor_key VARCHAR(64), 
	user_id INTEGER, 
	ip_address VARCHAR(60), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_news_comment_status CHECK (status IN ('approved','hidden')), 
	FOREIGN KEY(post_id) REFERENCES news_posts (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_news_comments_created_at ON news_comments (created_at);

CREATE INDEX ix_news_comments_post_id ON news_comments (post_id);

CREATE INDEX ix_news_comments_post_status ON news_comments (post_id, status);

CREATE INDEX ix_news_comments_status ON news_comments (status);

CREATE TABLE news_images (
	id SERIAL NOT NULL, 
	post_id INTEGER NOT NULL, 
	path VARCHAR(255) NOT NULL, 
	name VARCHAR(255), 
	mime VARCHAR(120), 
	size INTEGER, 
	alt VARCHAR(180), 
	position INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(post_id) REFERENCES news_posts (id) ON DELETE CASCADE
);

CREATE INDEX ix_news_images_post_id ON news_images (post_id);

CREATE TABLE news_reactions (
	id SERIAL NOT NULL, 
	post_id INTEGER NOT NULL, 
	visitor_key VARCHAR(64) NOT NULL, 
	user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_news_reaction_visitor UNIQUE (post_id, visitor_key), 
	FOREIGN KEY(post_id) REFERENCES news_posts (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_news_reactions_post_id ON news_reactions (post_id);

CREATE TABLE parent_students (
	parent_id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	relationship VARCHAR(40), 
	is_primary BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (parent_id, student_id), 
	FOREIGN KEY(parent_id) REFERENCES parents (id) ON DELETE CASCADE, 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
);

CREATE TABLE grades (
	id SERIAL NOT NULL, 
	student_id INTEGER NOT NULL, 
	course_id INTEGER NOT NULL, 
	assignment_id INTEGER, 
	period VARCHAR(20) NOT NULL, 
	score FLOAT NOT NULL, 
	max_score FLOAT NOT NULL, 
	observations VARCHAR(200), 
	recorded_by INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_grade_student_assignment UNIQUE (student_id, assignment_id, period), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(course_id) REFERENCES courses (id) ON DELETE CASCADE, 
	FOREIGN KEY(assignment_id) REFERENCES assignments (id) ON DELETE SET NULL, 
	FOREIGN KEY(recorded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_grades_student_id ON grades (student_id);
