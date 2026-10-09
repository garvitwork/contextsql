"""13 more synthetic domains (same mini-DSL as specs.py)."""
EXTRA = {
"insurance": """customers: name:name, city:city, birth_date:date(60), segment:cat(individual|family|corporate)
agents: name:name, region:cat(north|south|east|west), hire_date:date(8)
policies: customer_id:fk(customers), agent_id:fk(agents), policy_type:cat(auto|home|life|health), premium:money(100-5000), start_date:date(4), status:cat(active|lapsed|cancelled|expired)
claims: policy_id:fk(policies), claim_date:date(2), amount:money(100-50000), status:cat(open|approved|rejected|paid)""",
"airline": """aircraft: model:label, seats:int(50-400), is_active:flag
passengers: name:name, email:email, country:cat(USA|India|UK|Germany|Japan|Brazil), loyalty_tier:cat(none|silver|gold|platinum)
flights: aircraft_id:fk(aircraft), origin:city, destination:city, departure_date:date(2), status:cat(scheduled|departed|arrived|cancelled|delayed), distance_km:int(200-12000)
reservations: flight_id:fk(flights), passenger_id:fk(passengers), seat_class:cat(economy|business|first), fare:money(50-5000), status:cat(confirmed|cancelled|checked_in)""",
"telecom": """plans: name:label, monthly_price:money(5-120), data_gb:int(1-200)
subscribers: name:name, city:city, plan_id:fk(plans), joined_date:date(5), status:cat(active|suspended|churned)
usage_records: subscriber_id:fk(subscribers), record_date:date(1), minutes:int(0-600), data_mb:int(0-20000)
invoices: subscriber_id:fk(subscribers), amount:money(5-300), issued_date:date(2), paid:flag""",
"energy": """customers: name:name, city:city, customer_type:cat(residential|commercial|industrial)
meters: customer_id:fk(customers), install_date:date(8), meter_type:cat(smart|analog), is_active:flag
readings: meter_id:fk(meters), reading_date:date(1), kwh:int(10-5000)
outages: customer_id:fk(customers), outage_date:date(2), duration_hours:int(1-72), cause:cat(storm|equipment|maintenance|unknown)?""",
"agriculture": """farms: name:label, region:cat(north|south|east|west|central), area_acres:int(5-2000)
crops: name:label, season:cat(spring|summer|autumn|winter)
buyers: name:name, country:cat(USA|India|UK|Germany|Japan)
harvests: farm_id:fk(farms), crop_id:fk(crops), harvest_date:date(3), yield_tons:int(1-500), quality:cat(a|b|c)?
sales: harvest_id:fk(harvests), buyer_id:fk(buyers), price_per_ton:money(100-900), sale_date:date(2)""",
"construction": """projects: name:label, city:city, budget:money(100000-9000000), status:cat(planned|active|completed|cancelled)
workers: name:name, trade:cat(electrician|plumber|mason|carpenter|welder), hourly_rate:money(10-60)
tasks: project_id:fk(projects), worker_id:fk(workers), start_date:date(2), hours:int(1-200), status:cat(todo|in_progress|done|blocked)
materials: project_id:fk(projects), item:label, cost:money(50-20000), delivered:flag""",
"events": """venues: name:label, city:city, capacity:int(50-20000)
events: name:label, venue_id:fk(venues), event_date:date(2), category:cat(concert|conference|sports|festival), status:cat(scheduled|completed|cancelled)
attendees: name:name, email:email, city:city
tickets: event_id:fk(events), attendee_id:fk(attendees), price:money(5-500), purchase_date:date(2), status:cat(valid|refunded|used)""",
"nonprofit": """donors: name:name, email:email, city:city, donor_type:cat(individual|corporate|foundation)
campaigns: title:label, goal_amount:money(5000-500000), start_date:date(3), status:cat(planned|active|completed)
donations: donor_id:fk(donors), campaign_id:fk(campaigns), amount:money(5-20000), donation_date:date(3), recurring:flag
volunteers: name:name, city:city, joined_date:date(5), hours_given:int(0-500)""",
"auto_service": """owners: name:name, phone:code(1000000-9999999), city:city
vehicles: owner_id:fk(owners), make:cat(toyota|honda|ford|bmw|tesla), model_year:code(2005-2024), mileage:int(1000-250000)
service_jobs: vehicle_id:fk(vehicles), job_date:date(2), job_type:cat(oil_change|brakes|tires|engine|inspection), cost:money(30-3000), status:cat(booked|done|cancelled)
parts: job_id:fk(service_jobs), part_name:label, quantity:int(1-8), unit_cost:money(2-900)""",
"pharmacy": """suppliers: name:label, country:cat(USA|India|Germany|Switzerland|China)
drugs: name:label, supplier_id:fk(suppliers), category:cat(antibiotic|painkiller|vitamin|cardio|diabetes), unit_price:money(1-300)
purchase_orders: supplier_id:fk(suppliers), order_date:date(2), status:cat(pending|received|cancelled)
stock_levels: drug_id:fk(drugs), quantity:int(0-5000), expiry_date:date(2)""",
"recruiting": """jobs: title:label, department:cat(engineering|sales|marketing|finance|support), salary_max:money(30000-200000), status:cat(open|closed|on_hold)
candidates: name:name, email:email, city:city, years_experience:int(0-25)
applications: job_id:fk(jobs), candidate_id:fk(candidates), applied_date:date(1), stage:cat(applied|screening|interview|offer|hired|rejected)
interviews: application_id:fk(applications), interview_date:date(1), score:int(1-10)?, mode:cat(onsite|video|phone)""",
"streaming": """artists: name:name, country:cat(USA|India|UK|Korea|Brazil), genre:cat(pop|rock|hiphop|jazz|classical)
tracks: title:label, artist_id:fk(artists), duration_sec:int(60-600), released_year:code(1990-2024)
listeners: name:name, country:cat(USA|India|UK|Korea|Brazil), plan:cat(free|premium|family)
streams: track_id:fk(tracks), listener_id:fk(listeners), stream_date:date(1), seconds_played:int(5-600)""",
"ecommerce": """customers: name:name, email:email, country:cat(USA|India|UK|Germany|Japan), segment:cat(consumer|smb|enterprise)
products: name:label, category:cat(electronics|furniture|office|apparel), unit_price:money(5-900)
orders: customer_id:fk(customers), order_date:date(2), status:cat(shipped|delivered|pending|cancelled|returned), channel:cat(web|app|store)?
order_items: order_id:fk(orders), product_id:fk(products), quantity:int(1-6), unit_price:money(5-900), discount_pct:int(0-20)?
payments: order_id:fk(orders), amount:money(5-3000), method:cat(card|upi|bank|cash), payment_date:date(2)""",
}
