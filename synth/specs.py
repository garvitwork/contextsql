"""12 synthetic company databases: different domains, naming styles, and (un)declared foreign keys."""
import re

# kinds: pk-less DSL. name | label | email | city | money(lo-hi) | int(lo-hi) | code(lo-hi) | date(years) | cat(a|b|c) | flag | fk(parent)
# trailing ? = nullable column
SPECS = {
"hr": """departments: name:label, location:city, budget:money(50000-900000)
employees: name:name, email:email, department_id:fk(departments), hire_date:date(5), salary:money(30000-150000), level:cat(junior|mid|senior|lead), is_active:flag, phone:code(1000000-9999999)?
leave_requests: employee_id:fk(employees), start_date:date(2), days:int(1-20), leave_type:cat(annual|sick|unpaid), status:cat(pending|approved|rejected)""",
"clinic": """patients: name:name, email:email, city:city, birth_date:date(70), insurance:cat(none|basic|premium)?
doctors: name:name, specialty:cat(cardiology|pediatrics|orthopedics|dermatology|general), city:city
appointments: patient_id:fk(patients), doctor_id:fk(doctors), appointment_date:date(2), status:cat(scheduled|completed|cancelled|no_show), fee:money(30-400)
prescriptions: appointment_id:fk(appointments), medication:label, dosage_mg:int(5-500), days_supply:int(5-90)""",
"school": """teachers: name:name, subject:cat(math|science|english|history|art), hire_date:date(15)
courses: title:label, teacher_id:fk(teachers), credits:int(1-6), level:cat(beginner|intermediate|advanced)
students: name:name, email:email, city:city, enrolled_date:date(4), grade_level:int(1-12)
enrollments: student_id:fk(students), course_id:fk(courses), score:int(30-100)?, enroll_date:date(3), status:cat(active|completed|dropped)""",
"logistics": """warehouses: name:label, city:city, capacity:int(500-20000)
carriers: name:label, mode:cat(road|rail|air|sea)
shipments: warehouse_id:fk(warehouses), carrier_id:fk(carriers), ship_date:date(2), weight_kg:int(1-5000), status:cat(in_transit|delivered|delayed|lost), cost:money(20-9000)
vehicles: carrier_id:fk(carriers), plate:label, capacity_kg:int(1000-20000), is_active:flag""",
"saas": """accounts: company:label, country:cat(USA|India|UK|Germany|Brazil), plan:cat(free|pro|enterprise), created_date:date(3)
subscriptions: account_id:fk(accounts), start_date:date(2), monthly_fee:money(10-2000), status:cat(active|cancelled|paused)
invoices: subscription_id:fk(subscriptions), amount:money(10-2000), issued_date:date(2), paid:flag
support_tickets: account_id:fk(accounts), priority:cat(low|medium|high|urgent), opened_date:date(2), resolved_date:date(2)?, category:cat(billing|bug|feature|access)""",
"bank": """customers: name:name, city:city, joined_date:date(10), segment:cat(retail|premium|business)
accounts: customer_id:fk(customers), account_type:cat(savings|checking|fixed_deposit), balance:money(0-200000), opened_date:date(8), is_active:flag
transactions: account_id:fk(accounts), amount:money(5-20000), txn_date:date(2), txn_type:cat(deposit|withdrawal|transfer|payment)
loans: customer_id:fk(customers), principal:money(1000-500000), interest_rate:int(3-18), status:cat(active|closed|defaulted), start_date:date(6)""",
"realestate": """agents: name:name, email:email, city:city, hire_date:date(8)
properties: address:label, city:city, bedrooms:int(1-6), area_sqft:int(300-6000), property_type:cat(apartment|house|villa|office)
listings: property_id:fk(properties), agent_id:fk(agents), list_price:money(30000-2000000), listed_date:date(2), status:cat(active|sold|withdrawn)
viewings: listing_id:fk(listings), viewing_date:date(1), visitor_name:name, rating:int(1-5)?""",
"library": """authors: name:name, country:cat(USA|India|UK|France|Japan)
books: title:label, author_id:fk(authors), genre:cat(fiction|science|history|biography|children), pages:int(50-1200), published_year:code(1950-2024)
members: name:name, email:email, city:city, joined_date:date(6)
loans: book_id:fk(books), member_id:fk(members), loan_date:date(2), due_days:int(7-30), returned:flag""",
"restaurant": """staff: name:name, role:cat(chef|waiter|manager|cashier), hire_date:date(6), hourly_wage:money(8-40)
menu_items: name:label, category:cat(starter|main|dessert|drink), price:money(3-60), is_vegetarian:flag
orders: staff_id:fk(staff), order_date:date(1), table_no:code(1-30), status:cat(open|paid|cancelled), tip:money(0-30)?
order_lines: order_id:fk(orders), menu_item_id:fk(menu_items), quantity:int(1-6)""",
"hotel": """guests: name:name, email:email, country:cat(USA|India|UK|Germany|Japan), vip:flag
rooms: room_no:code(100-999), room_type:cat(single|double|suite|family), price_per_night:money(40-600), floor:int(1-12)
bookings: guest_id:fk(guests), room_id:fk(rooms), check_in:date(2), nights:int(1-14), status:cat(confirmed|cancelled|checked_out), channel:cat(web|phone|agent|walk_in)?
payments: booking_id:fk(bookings), amount:money(40-5000), method:cat(card|cash|transfer), paid_date:date(2)""",
"manufacturing": """machines: name:label, line:cat(A|B|C|D), installed_date:date(10), is_active:flag
products: name:label, category:cat(parts|assembly|packaging|tools), unit_cost:money(1-500)
work_orders: product_id:fk(products), machine_id:fk(machines), start_date:date(2), quantity:int(10-5000), status:cat(planned|running|done|cancelled)
defects: work_order_id:fk(work_orders), defect_type:cat(crack|scratch|misalign|leak), defect_count:int(1-50), found_date:date(1)""",
"gym": """members: name:name, email:email, city:city, joined_date:date(4), plan:cat(basic|standard|premium)
trainers: name:name, specialty:cat(yoga|strength|cardio|boxing), hourly_rate:money(15-120)
classes: title:label, trainer_id:fk(trainers), weekday:cat(mon|tue|wed|thu|fri|sat|sun), capacity:int(8-40)
attendance: class_id:fk(classes), member_id:fk(members), attend_date:date(1), checked_in:flag""",
}

# naming style per database. pk: "id" or "table_id".  col: snake | camel | prefixed.
STYLES = {
"hr":            dict(tbl="",     col="snake",    abbr=False, pk="id",       fk_declared=True),
"clinic":        dict(tbl="tbl_", col="snake",    abbr=True,  pk="table_id", fk_declared=False),
"school":        dict(tbl="",     col="camel",    abbr=False, pk="table_id", fk_declared=True),
"logistics":     dict(tbl="t_",   col="prefixed", abbr=True,  pk="id",       fk_declared=False),
"saas":          dict(tbl="",     col="snake",    abbr=False, pk="id",       fk_declared=False),
"bank":          dict(tbl="",     col="snake",    abbr=True,  pk="table_id", fk_declared=True),
"realestate":    dict(tbl="tbl_", col="camel",    abbr=False, pk="id",       fk_declared=False),
"library":       dict(tbl="",     col="prefixed", abbr=False, pk="table_id", fk_declared=True),
"restaurant":    dict(tbl="",     col="snake",    abbr=True,  pk="id",       fk_declared=False),
"hotel":         dict(tbl="tbl_", col="camel",    abbr=True,  pk="table_id", fk_declared=False),
"manufacturing": dict(tbl="",     col="prefixed", abbr=True,  pk="id",       fk_declared=False),
"gym":           dict(tbl="",     col="snake",    abbr=False, pk="table_id", fk_declared=True),
}
HELD_OUT = {"hotel", "manufacturing", "gym"}
DB_PREFIX = "synth_"

def parse(text):
    tables = {}
    for line in text.strip().splitlines():
        t, rest = line.split(":", 1)
        cols = []
        for part in rest.split(","):
            m = re.match(r"\s*(\w+):(\w+)(?:\(([^)]*)\))?(\?)?\s*$", part)
            cols.append(dict(logical=m.group(1), kind=m.group(2), args=m.group(3) or "", nullable=bool(m.group(4))))
        tables[t.strip()] = cols
    return tables
