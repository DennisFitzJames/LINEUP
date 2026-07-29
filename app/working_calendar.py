from datetime import datetime, date, timedelta

FULL_NORMAL_DAY_MINUTES = 475

MONDAY_TO_THURSDAY_BLOCKS = [
    (7 * 60 + 45, 10 * 60),
    (10 * 60 + 10, 12 * 60 + 30),
    (13 * 60 + 15, 16 * 60 + 35),
]

FRIDAY_BLOCKS = [
    (7 * 60 + 45, 10 * 60),
    (10 * 60 + 10, 13 * 60 + 10),
]


def coerce_date(value):
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return date.today()


def is_working_day(day):
    day = coerce_date(day)
    return day.weekday() < 5


def working_blocks_for_day(day):
    day = coerce_date(day)

    if not is_working_day(day):
        return []

    if day.weekday() == 4:
        return FRIDAY_BLOCKS

    return MONDAY_TO_THURSDAY_BLOCKS


def working_minutes_for_day(day):
    total = 0

    for block_start, block_end in working_blocks_for_day(day):
        total += block_end - block_start

    return total


def first_working_day_on_or_after(day):
    day = coerce_date(day)

    while not is_working_day(day):
        day += timedelta(days=1)

    return day


def next_working_day(day):
    day = coerce_date(day)
    next_day = day + timedelta(days=1)

    while not is_working_day(next_day):
        next_day += timedelta(days=1)

    return next_day


def previous_working_day(day):
    day = coerce_date(day)
    previous_day = day - timedelta(days=1)

    while not is_working_day(previous_day):
        previous_day -= timedelta(days=1)

    return previous_day


def add_working_days(start_day, working_day_offset):
    start_day = coerce_date(start_day)
    working_day_offset = int(working_day_offset)

    if working_day_offset == 0:
        return first_working_day_on_or_after(start_day)

    if working_day_offset > 0:
        current_day = start_day
        remaining = working_day_offset

        while remaining > 0:
            current_day += timedelta(days=1)

            if is_working_day(current_day):
                remaining -= 1

        return current_day

    current_day = start_day
    remaining = abs(working_day_offset)

    while remaining > 0:
        current_day -= timedelta(days=1)

        if is_working_day(current_day):
            remaining -= 1

    return current_day


def working_day_offset_between(start_day, target_day):
    start_day = coerce_date(start_day)

    if target_day is None:
        return ""

    target_day = coerce_date(target_day)

    if target_day == start_day:
        return 0

    if target_day > start_day:
        offset = 0
        current_day = start_day

        while current_day < target_day:
            current_day += timedelta(days=1)

            if is_working_day(current_day):
                offset += 1

        return offset

    offset = 0
    current_day = start_day

    while current_day > target_day:
        if is_working_day(current_day):
            offset -= 1

        current_day -= timedelta(days=1)

    return offset


def elapsed_working_minutes_in_day(moment):
    if moment is None:
        return 0

    if not is_working_day(moment.date()):
        return 0

    current_minutes = moment.hour * 60 + moment.minute
    total = 0

    for block_start, block_end in working_blocks_for_day(moment.date()):
        if current_minutes <= block_start:
            break

        if block_start < current_minutes < block_end:
            total += current_minutes - block_start
            break

        if current_minutes >= block_end:
            total += block_end - block_start

    return min(total, working_minutes_for_day(moment.date()))


def working_minutes_between(start_dt, end_dt=None):
    if start_dt is None:
        return 0

    if end_dt is None:
        end_dt = datetime.now()

    if end_dt <= start_dt:
        return 0

    total = 0
    current_day = start_dt.date()
    end_day = end_dt.date()

    while current_day <= end_day:
        blocks = working_blocks_for_day(current_day)

        if not blocks:
            current_day += timedelta(days=1)
            continue

        if current_day == start_dt.date():
            start_minutes = start_dt.hour * 60 + start_dt.minute
        else:
            start_minutes = 0

        if current_day == end_dt.date():
            end_minutes = end_dt.hour * 60 + end_dt.minute
        else:
            end_minutes = 24 * 60

        for block_start, block_end in blocks:
            overlap_start = max(start_minutes, block_start)
            overlap_end = min(end_minutes, block_end)

            if overlap_end > overlap_start:
                total += overlap_end - overlap_start

        current_day += timedelta(days=1)

    return max(0, total)


def work_minute_start_for_datetime(base_date, moment):
    base_date = coerce_date(base_date)

    if moment is None:
        moment = datetime.now()

    target_day = moment.date()
    total = 0
    current_day = base_date

    while current_day < target_day:
        total += working_minutes_for_day(current_day)
        current_day += timedelta(days=1)

    if target_day >= base_date:
        total += elapsed_working_minutes_in_day(moment)

    return max(0, total)


def current_work_minute_start(base_date=None):
    if base_date is None:
        base_date = date.today()

    return work_minute_start_for_datetime(base_date, datetime.now())


def work_minute_to_day_and_minute(base_date, work_minute, is_finish=False):
    base_date = coerce_date(base_date)
    remaining = max(0, int(work_minute))
    current_day = base_date

    safety_counter = 0

    while safety_counter < 4000:
        day_capacity = working_minutes_for_day(current_day)

        if day_capacity <= 0:
            current_day += timedelta(days=1)
            safety_counter += 1
            continue

        if is_finish:
            if remaining <= day_capacity:
                return current_day, remaining
        else:
            if remaining < day_capacity:
                return current_day, remaining

        remaining -= day_capacity
        current_day += timedelta(days=1)
        safety_counter += 1

    return current_day, 0


def minute_in_workday_to_clock(day, minute_in_day, is_finish=False):
    minute_in_day = max(0, int(minute_in_day))
    remaining = minute_in_day
    blocks = working_blocks_for_day(day)

    if not blocks:
        return 0

    for block_start, block_end in blocks:
        block_length = block_end - block_start

        if is_finish:
            if remaining <= block_length:
                return block_start + remaining
        else:
            if remaining < block_length:
                return block_start + remaining

        remaining -= block_length

    return blocks[-1][1]


def day_label(base_date, target_day):
    base_date = coerce_date(base_date)
    target_day = coerce_date(target_day)

    if target_day == base_date:
        return ""

    return target_day.strftime("%a %d/%m ")


def work_minute_to_shift_time(base_date, work_minute, is_finish=False):
    target_day, minute_in_day = work_minute_to_day_and_minute(
        base_date,
        work_minute,
        is_finish=is_finish
    )

    clock_minutes = minute_in_workday_to_clock(
        target_day,
        minute_in_day,
        is_finish=is_finish
    )

    hours = clock_minutes // 60
    minutes = clock_minutes % 60

    return f"{day_label(base_date, target_day)}{hours:02d}:{minutes:02d}".strip()


def planned_day_offset(base_date, work_minute, is_finish=False):
    target_day, _minute_in_day = work_minute_to_day_and_minute(
        base_date,
        work_minute,
        is_finish=is_finish
    )

    return working_day_offset_between(base_date, target_day)


def working_calendar_summary():
    return {
        "monday_to_thursday_minutes": working_minutes_for_day(date(2026, 1, 5)),
        "friday_minutes": working_minutes_for_day(date(2026, 1, 9)),
        "monday_to_thursday_blocks": MONDAY_TO_THURSDAY_BLOCKS,
        "friday_blocks": FRIDAY_BLOCKS,
    }


if __name__ == "__main__":
    print()
    print("===================================")
    print("LINEUP Working Calendar")
    print("===================================")
    print("Monday to Thursday:")
    print("  07:45-10:00")
    print("  10:10-12:30")
    print("  13:15-16:35")
    print(f"  Total: {working_minutes_for_day(date(2026, 1, 5))} min")
    print()
    print("Friday:")
    print("  07:45-10:00")
    print("  10:10-13:10")
    print(f"  Total: {working_minutes_for_day(date(2026, 1, 9))} min")
    print()