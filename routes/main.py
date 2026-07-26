from flask import Blueprint, render_template
from models import MenuItem, DailyMenu, Settings
from datetime import date
from utils.helpers import get_setting

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    today = date.today()
    # Get today's menu items
    daily = DailyMenu.query.filter_by(date=today).all()
    today_items = [d.menu_item for d in daily if d.menu_item.is_available]

    settings = {
        'college_name': get_setting('college_name', 'Your College Name'),
        'canteen_name': get_setting('canteen_name', 'College Canteen'),
        'canteen_open': get_setting('canteen_open', '08:00'),
        'canteen_close': get_setting('canteen_close', '16:00'),
        'developer': get_setting('developer', 'Sakib'),
    }
    return render_template('main/index.html', today_items=today_items, settings=settings)
