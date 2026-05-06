from datetime import date, timedelta


def get_week_monday(value: date) -> date:
    return value - timedelta(days=value.isoweekday() - 1)


def get_semester_week_monday(start_date: date, week_number: int) -> date:
    if week_number < 1:
        raise ValueError("week_number must be at least 1")
    return get_week_monday(start_date) + timedelta(days=(week_number - 1) * 7)


def get_semester_weekday_date(
    start_date: date, week_number: int, day_of_week: int
) -> date:
    if day_of_week < 1 or day_of_week > 7:
        raise ValueError("day_of_week must be between 1 and 7")
    return get_semester_week_monday(start_date, week_number) + timedelta(
        days=day_of_week - 1
    )


def count_semester_weeks(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")
    start_monday = get_week_monday(start_date)
    end_monday = get_week_monday(end_date)
    return ((end_monday - start_monday).days // 7) + 1
