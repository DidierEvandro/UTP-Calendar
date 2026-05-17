from calendar import monthrange
from datetime import date, datetime

def _add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, monthrange(year, month)[1])
    return date(year, month, day)

def calculate_extraction_window(settings: dict, today: date) -> tuple[date, date]:
    use_custom = settings.get("use_custom_date_range", settings.get("UseCustomDateRange", False))
    min_date = today.replace(day=1)
    max_date = _add_months(today, 3) 
    
    if use_custom:
        start_str = settings.get("custom_start_date", settings.get("CustomStartDate"))
        end_str = settings.get("custom_end_date", settings.get("CustomEndDate"))
        
        try: start_d = datetime.fromisoformat(str(start_str)[:10]).date() if start_str else min_date
        except: start_d = min_date
        
        try: end_d = datetime.fromisoformat(str(end_str)[:10]).date() if end_str else max_date
        except: end_d = max_date
        
        start_d = max(start_d, min_date)
        end_d = min(end_d, max_date)
        if end_d < start_d: end_d = start_d
        
        return start_d, end_d
    else:
        months = int(settings.get("search_range_months", settings.get("SearchRangeMonths", 2)))
        months = max(1, min(3, months))
        
        start_d = min_date
        target_month = _add_months(start_d, months - 1)
        end_d = date(target_month.year, target_month.month, monthrange(target_month.year, target_month.month)[1])
        
        return start_d, end_d

def parse_date(value: str) -> date: return datetime.strptime(value.strip(), "%d-%m-%Y").date()
def format_date(value: date) -> str: return value.strftime("%d-%m-%Y")
def format_datetime(value: datetime) -> str: return value.strftime("%d-%m-%Y %H:%M:%S")