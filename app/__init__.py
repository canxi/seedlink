"""
Flask 应用工厂模块

功能说明：
    1. 创建和配置 Flask 应用实例
    2. 初始化数据库连接
    3. 注册蓝图（路由）

设计模式：
    使用工厂模式，便于测试和扩展
"""

import os
import logging
from flask import Flask
from app.models import db
from app.config import config


def create_app():
    """
    创建并配置 Flask 应用实例

    Returns:
        Flask: 配置好的 Flask 应用对象
    """
    # 获取项目根目录路径
    # __file__ = app/__init__.py
    # 第一次 dirname 得到 app/ 目录
    # 第二次 dirname 得到项目根目录
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    # 创建 Flask 实例，指定模板和静态文件目录
    # 由于我们的目录结构不是标准的 app/ 下存放模板，
    # 所以需要显式指定路径
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # 从环境变量获取密钥，没有则使用默认值
    # 用于会话安全和 CSRF 保护
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pt-hardlink-manager-secret-key')

    # 配置 SQLite 数据库 URI
    # 格式：sqlite:///相对路径 或 sqlite:////绝对路径
    app.config['SQLALCHEMY_DATABASE_URI'] = config.database_uri

    # 禁用 Flask-SQLAlchemy 的事件系统，减少内存开销
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 配置日志格式和级别
    # debug=True 时输出详细日志，便于开发调试
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 初始化 SQLAlchemy 数据库连接
    db.init_app(app)

    # 在应用上下文中创建所有数据库表
    # 相当于执行 CREATE TABLE IF NOT EXISTS ...
    with app.app_context():
        db.create_all()

    # 注册蓝图
    # 蓝图将路由组织成模块，便于管理
    from app.routes import bp
    app.register_blueprint(bp)

    return app
