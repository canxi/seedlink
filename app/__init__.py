import os
import logging
from flask import Flask
from app.models import db
from app.config import config


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pt-hardlink-manager-secret-key')

    # 确保数据库目录存在
    db_path = '/data/hardlinks.db'
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    app.config['SQLALCHEMY_DATABASE_URI'] = config.database_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    db.init_app(app)

    with app.app_context():
        db.create_all()

    from app.routes import bp
    app.register_blueprint(bp)

    return app
