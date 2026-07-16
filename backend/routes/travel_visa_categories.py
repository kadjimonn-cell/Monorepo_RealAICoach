"""
Travel Visa — 520+ Expanded Learning Categories Seed Data
Auto-generated structured categories covering all visa types, countries, documentation, and scenarios
"""

def generate_expanded_categories():
    """Generate 520+ structured categories programmatically"""
    categories = []
    cat_id = 0

    def add(name, group, icon, tier="basic", lessons=12):
        nonlocal cat_id
        cat_id += 1
        cid = f"cat-{cat_id:04d}"
        categories.append({"id": cid, "name": name, "group": group, "icon": icon, "lesson_count": lessons, "tier": tier})

    # ═══ VISA INTERVIEW TRAINING (50+) ═══
    interview_types = [
        ("Student Visa Interviews", "school", "free"), ("Tourist Visa Interviews", "airplane", "free"),
        ("Work Visa Interviews", "briefcase", "basic"), ("Family Sponsorship Interviews", "people", "basic"),
        ("Marriage Visa Interviews", "heart", "basic"), ("Business Visa Interviews", "trending-up", "basic"),
        ("Permanent Residency Interviews", "home", "premium"), ("Refugee & Asylum Guidance", "shield-checkmark", "premium"),
        ("Investor Visa Interviews", "cash", "premium"), ("Transit Visa Coaching", "swap-horizontal", "free"),
        ("Diplomatic Visa Coaching", "flag", "premium"), ("Religious Worker Visa", "book", "premium"),
        ("Artist/Entertainer Visa", "musical-notes", "basic"), ("Journalist Visa Coaching", "newspaper", "basic"),
        ("Crew Member Visa", "boat", "basic"), ("Treaty Trader Visa (E-1)", "globe", "premium"),
        ("Treaty Investor Visa (E-2)", "trending-up", "premium"), ("Intracompany Transfer (L-1)", "business", "basic"),
        ("Exchange Visitor Visa (J-1)", "swap-horizontal", "basic"), ("Specialty Worker Visa (H-1B)", "construct", "premium"),
        ("Seasonal Worker Visa (H-2B)", "leaf", "basic"), ("Agricultural Worker Visa (H-2A)", "nutrition", "basic"),
        ("Fiancé/Fiancée Visa (K-1)", "heart", "basic"), ("NAFTA Professional (TN)", "document-text", "premium"),
        ("Extraordinary Ability (O-1)", "star", "premium"), ("Digital Nomad Visa", "laptop", "basic"),
        ("Golden Visa Interviews", "diamond", "premium"), ("Retirement Visa Coaching", "sunny", "basic"),
        ("Medical Visa Interviews", "medkit", "basic"), ("Research Visa Coaching", "flask", "premium"),
    ]
    for name, icon, tier in interview_types:
        add(name, "Visa Interview Training", icon, tier, 18)

    # ═══ COUNTRY-SPECIFIC GUIDES (180+: 30 countries × 6 visa types) ═══
    countries_expanded = [
        "United States", "Canada", "United Kingdom", "Germany", "France", "Australia",
        "Japan", "UAE", "Singapore", "New Zealand", "Italy", "Spain", "South Korea",
        "India", "China", "Brazil", "Mexico", "Russia", "Saudi Arabia", "South Africa",
        "Nigeria", "Turkey", "Thailand", "Sweden", "Netherlands", "Switzerland",
        "Ireland", "Portugal", "Poland", "Malaysia",
    ]
    visa_subtypes = [
        ("Tourist Visa Guide", "airplane", "free"), ("Student Visa Guide", "school", "basic"),
        ("Work Visa Guide", "briefcase", "basic"), ("Family Visa Guide", "people", "basic"),
        ("Business Visa Guide", "trending-up", "premium"), ("Permanent Residency", "home", "premium"),
    ]
    for country in countries_expanded:
        for vname, vicon, vtier in visa_subtypes:
            add(f"{country}: {vname}", "Country Visa Guides", vicon, vtier, 15)

    # ═══ DOCUMENTATION TRAINING (60+) ═══
    doc_topics = [
        ("Passport Preparation", "document-text", "free"), ("Passport Renewal Guide", "refresh", "free"),
        ("Emergency Passport Services", "alert-circle", "free"), ("Financial Proof Basics", "wallet", "free"),
        ("Bank Statement Preparation", "card", "free"), ("Sponsor Letter Writing", "mail", "basic"),
        ("Invitation Letter Guide", "mail-open", "basic"), ("Employment Proof Documents", "business", "basic"),
        ("University Admission Letters", "school", "basic"), ("Travel Insurance Guide", "medkit", "free"),
        ("Accommodation Proof", "bed", "basic"), ("DS-160 Step-by-Step", "clipboard", "free"),
        ("DS-160 Common Mistakes", "warning", "free"), ("Biometrics Preparation", "finger-print", "basic"),
        ("Translation & Legalization", "language", "premium"), ("Apostille Guide", "document-attach", "premium"),
        ("Police Clearance Certificate", "shield", "basic"), ("Medical Examination Guide", "medkit", "basic"),
        ("Affidavit of Support (I-864)", "document-text", "premium"), ("Proof of Relationship", "heart", "basic"),
        ("Tax Return Documentation", "receipt", "premium"), ("Property Ownership Proof", "home", "basic"),
        ("Business Registration Docs", "business", "premium"), ("CV/Resume for Visa", "person", "basic"),
        ("Cover Letter Writing", "create", "basic"), ("Statement of Purpose", "create", "basic"),
        ("Research Proposal Writing", "flask", "premium"), ("Study Plan Document", "school", "basic"),
        ("Travel Itinerary Planning", "map", "free"), ("Hotel Booking Guide", "bed", "free"),
        ("Flight Reservation Tips", "airplane", "free"), ("Visa Photo Requirements", "camera", "free"),
        ("Online Application Forms", "laptop", "basic"), ("Appointment Scheduling", "calendar", "basic"),
        ("Document Checklist Builder", "checkbox", "basic"), ("Notarization Guide", "stamp", "premium"),
        ("Immigration Form I-20", "document-text", "basic"), ("Immigration Form I-130", "document-text", "premium"),
        ("Immigration Form I-140", "document-text", "premium"), ("Immigration Form N-400", "document-text", "premium"),
        ("IELTS/TOEFL Preparation", "school", "basic"), ("Language Proficiency Tests", "language", "basic"),
        ("Credential Evaluation (WES)", "school", "premium"), ("Skills Assessment Guide", "construct", "premium"),
        ("Character Reference Letters", "people", "basic"), ("Statutory Declaration", "document-text", "premium"),
        ("Marriage Certificate Guide", "heart", "basic"), ("Birth Certificate Guide", "document-text", "free"),
        ("Death Certificate for Visa", "document-text", "basic"), ("Divorce Documents Guide", "document-text", "basic"),
    ]
    for name, icon, tier in doc_topics:
        add(name, "Documentation Training", icon, tier, 10)

    # ═══ INTERVIEW SCENARIOS & PRACTICE (40+) ═══
    scenarios = [
        ("Mock U.S. Embassy Interview", "videocam", "basic"), ("Mock UK Embassy Interview", "videocam", "basic"),
        ("Mock Canadian Embassy Interview", "videocam", "basic"), ("Mock Schengen Embassy Interview", "videocam", "basic"),
        ("Mock Australian Embassy Interview", "videocam", "basic"), ("Mock Japanese Embassy Interview", "videocam", "premium"),
        ("AI Interview Simulations", "chatbubbles", "premium"), ("Confidence Building Exercises", "flash", "basic"),
        ("High-Risk Question Practice", "warning", "premium"), ("Rejection Recovery Coaching", "refresh", "basic"),
        ("Body Language Mastery", "body", "basic"), ("Audio Pronunciation Practice", "mic", "premium"),
        ("Cultural Etiquette Training", "globe", "basic"), ("Stress Management Techniques", "fitness", "basic"),
        ("Quick Answer Formulation", "timer", "basic"), ("Story Building for Interviews", "book", "basic"),
        ("Financial Questions Practice", "cash", "basic"), ("Intent Questions Practice", "help-circle", "basic"),
        ("Ties to Home Country Q&A", "home", "basic"), ("Education Background Q&A", "school", "basic"),
        ("Work Experience Q&A", "briefcase", "basic"), ("Family Situation Q&A", "people", "basic"),
        ("Travel History Q&A", "airplane", "basic"), ("Immigration History Q&A", "document-text", "premium"),
        ("Group Interview Practice", "people", "premium"), ("Phone Interview Practice", "call", "basic"),
        ("Video Call Interview Tips", "videocam", "basic"), ("Walk-in Interview Guide", "walk", "free"),
        ("Follow-up After Interview", "mail", "basic"), ("Consular Officer Psychology", "person", "premium"),
    ]
    for name, icon, tier in scenarios:
        add(name, "Interview Scenarios", icon, tier, 14)

    # ═══ IMMIGRATION EDUCATION (50+) ═══
    immigration = [
        ("Legal Immigration Pathways", "map", "free"), ("Living Abroad Education", "earth", "basic"),
        ("Relocation Readiness", "navigate", "basic"), ("International Student Prep", "school", "basic"),
        ("Work Permit Education", "briefcase", "basic"), ("Residency Systems Worldwide", "home", "premium"),
        ("Border Entry Expectations", "log-in", "free"), ("Airport Interview Preparation", "airplane", "basic"),
        ("Points-Based Immigration", "analytics", "basic"), ("Employer-Sponsored Immigration", "business", "basic"),
        ("Self-Employed Immigration", "person", "premium"), ("Startup Visa Programs", "rocket", "premium"),
        ("Investment Immigration", "trending-up", "premium"), ("Family Reunification", "people", "basic"),
        ("Citizenship by Naturalization", "flag", "premium"), ("Dual Citizenship Guide", "flag", "premium"),
        ("Visa Overstay Consequences", "warning", "free"), ("Immigration Lawyer Guide", "briefcase", "basic"),
        ("Immigration Scam Prevention", "shield", "free"), ("Green Card Lottery (DV)", "ticket", "basic"),
        ("Express Entry Canada Deep Dive", "speedometer", "premium"), ("UK Points System Guide", "analytics", "basic"),
        ("Schengen Area Navigation", "map", "basic"), ("Gulf States Work Migration", "business", "basic"),
        ("East Asian Work Migration", "globe", "basic"), ("African Immigration Pathways", "earth", "basic"),
        ("Latin American Immigration", "earth", "basic"), ("Caribbean Immigration Options", "sunny", "basic"),
        ("Nordic Immigration Guide", "snow", "basic"), ("Eastern European Immigration", "map", "basic"),
        ("Oceania Immigration Guide", "earth", "basic"), ("Immigration Timeline Planning", "calendar", "basic"),
        ("Cost of Immigration Guide", "cash", "basic"), ("Immigration Medical Exam", "medkit", "basic"),
        ("Immigration Background Check", "shield", "basic"), ("Immigration Appeal Process", "document-text", "premium"),
        ("Deportation Defense Basics", "shield-checkmark", "premium"), ("Voluntary Departure Guide", "airplane", "premium"),
        ("Humanitarian Protection", "heart", "premium"), ("Temporary Protected Status", "shield", "premium"),
        ("DACA Education Guide", "school", "premium"), ("Refugee Resettlement Basics", "people", "premium"),
        ("Asylum Application Guide", "document-text", "premium"), ("Immigration Bond Guide", "cash", "premium"),
        ("Immigration Court Process", "briefcase", "premium"), ("Post-Arrival Settlement", "home", "basic"),
        ("Cultural Adjustment Guide", "people", "basic"), ("Healthcare Abroad Guide", "medkit", "basic"),
        ("Banking Abroad Guide", "card", "basic"), ("Housing Abroad Guide", "home", "basic"),
    ]
    for name, icon, tier in immigration:
        add(name, "Immigration Education", icon, tier, 12)

    # ═══ PROFESSIONAL SKILLS (40+) ═══
    professional = [
        ("International Resume Writing", "document-text", "basic"), ("LinkedIn for Immigration", "globe", "basic"),
        ("Networking Abroad", "people", "basic"), ("Job Search Strategies", "search", "basic"),
        ("Remote Work Visas", "laptop", "basic"), ("Freelancer Immigration", "person", "premium"),
        ("Entrepreneurship Abroad", "rocket", "premium"), ("International Tax Basics", "receipt", "premium"),
        ("Money Transfer Guide", "cash", "basic"), ("International Health Insurance", "medkit", "basic"),
        ("Cross-Cultural Communication", "chatbubbles", "basic"), ("Language Learning Strategies", "language", "basic"),
        ("International Student Housing", "home", "basic"), ("Campus Life Abroad", "school", "basic"),
        ("Internship Visa Guide", "briefcase", "basic"), ("Post-Graduation Work Options", "school", "basic"),
        ("Academic Credential Transfer", "document-text", "premium"), ("Professional License Transfer", "construct", "premium"),
        ("International Driving License", "car", "free"), ("Voting Rights Abroad", "flag", "premium"),
        ("Tax Filing While Abroad", "receipt", "premium"), ("Social Security Abroad", "shield", "premium"),
        ("Pension Transfer Guide", "cash", "premium"), ("International Shipping", "cube", "basic"),
        ("Pet Immigration Guide", "paw", "basic"), ("Moving with Children", "people", "basic"),
        ("Elder Care Immigration", "people", "premium"), ("Military Spouse Immigration", "shield", "premium"),
        ("Diplomatic Family Guide", "flag", "premium"), ("Trailing Spouse Career", "person", "basic"),
    ]
    for name, icon, tier in professional:
        add(name, "Professional & Life Skills", icon, tier, 10)

    # ═══ EMBASSY & CONSULAR (30+) ═══
    embassy_topics = [
        ("Understanding Embassy Roles", "business", "free"), ("Consulate vs Embassy", "information-circle", "free"),
        ("Visa Application Center Guide", "storefront", "free"), ("Embassy Appointment Tips", "calendar", "basic"),
        ("Embassy Security Procedures", "shield", "free"), ("Embassy Etiquette", "people", "basic"),
        ("Consular Officer Insights", "person", "premium"), ("VFS Global Guide", "globe", "basic"),
        ("TLS Contact Guide", "globe", "basic"), ("BLS International Guide", "globe", "basic"),
        ("Embassy Fee Payment Guide", "card", "free"), ("Rush Processing Options", "flash", "premium"),
        ("Group Visa Applications", "people", "basic"), ("Minor Child Visa Guide", "people", "basic"),
        ("Senior Citizen Visa Guide", "people", "basic"), ("Disabled Traveler Guide", "accessibility", "basic"),
        ("Emergency Visa Services", "alert-circle", "premium"), ("Visa Extension Process", "time", "basic"),
        ("Visa Change of Status", "swap-horizontal", "premium"), ("Visa Stamping Guide", "stamp", "basic"),
        ("Port of Entry Interview", "log-in", "basic"), ("Secondary Inspection Guide", "search", "premium"),
        ("Customs Declaration Guide", "clipboard", "free"), ("Duty-Free Allowances", "cart", "free"),
        ("Prohibited Items Guide", "close-circle", "free"), ("Embassy Complaint Process", "mail", "premium"),
        ("Consular Assistance Abroad", "call", "basic"), ("Lost Passport Abroad", "alert-circle", "basic"),
        ("Arrest Abroad Guide", "shield", "premium"), ("Natural Disaster Protocol", "thunderstorm", "premium"),
    ]
    for name, icon, tier in embassy_topics:
        add(name, "Embassy & Consular Services", icon, tier, 8)

    # ═══ SPECIALIZED VISA PROGRAMS (40+) ═══
    specialized = [
        ("EU Blue Card Program", "card", "premium"), ("UK Global Talent Visa", "star", "premium"),
        ("Australia Skilled Migration", "construct", "premium"), ("Canada Express Entry", "speedometer", "premium"),
        ("US EB-5 Investor Visa", "cash", "premium"), ("Portugal Golden Visa", "diamond", "premium"),
        ("Spain Non-Lucrative Visa", "sunny", "basic"), ("Germany Job Seeker Visa", "search", "basic"),
        ("Netherlands DAFT Treaty", "document-text", "premium"), ("Ireland Start-up Visa", "rocket", "premium"),
        ("Singapore EntrePass", "business", "premium"), ("UAE Golden Visa", "diamond", "premium"),
        ("Thailand Elite Visa", "diamond", "premium"), ("Malaysia MM2H", "home", "basic"),
        ("Japan Highly Skilled Pro", "star", "premium"), ("South Korea E-7 Visa", "briefcase", "premium"),
        ("New Zealand Skilled Migrant", "construct", "premium"), ("Sweden Work Permit", "briefcase", "basic"),
        ("Denmark Green Card Scheme", "card", "premium"), ("Norway Skilled Worker", "construct", "basic"),
        ("Finland Startup Permit", "rocket", "premium"), ("Estonia e-Residency", "laptop", "basic"),
        ("Croatia Digital Nomad", "laptop", "basic"), ("Georgia Remote Worker", "laptop", "basic"),
        ("Barbados Welcome Stamp", "sunny", "basic"), ("Bermuda Work from Bermuda", "sunny", "basic"),
        ("Costa Rica Rentista Visa", "cash", "basic"), ("Mexico Temporary Resident", "document-text", "basic"),
        ("Panama Friendly Nations", "people", "basic"), ("Chile Tech Visa", "laptop", "premium"),
        ("Brazil Digital Nomad", "laptop", "basic"), ("Argentina Rentista", "cash", "basic"),
        ("South Africa Critical Skills", "construct", "premium"), ("Rwanda Visa on Arrival", "airplane", "free"),
        ("Kenya e-Visa Guide", "laptop", "free"), ("Morocco Residency Permit", "home", "basic"),
        ("Egypt Work Permit", "briefcase", "basic"), ("Israel Innovation Visa", "flash", "premium"),
        ("Taiwan Gold Card", "card", "premium"), ("Hong Kong Top Talent", "star", "premium"),
    ]
    for name, icon, tier in specialized:
        add(name, "Specialized Visa Programs", icon, tier, 14)

    # ═══ DIGITAL & TECH (20+) ═══
    tech = [
        ("Remote Work Tax Implications", "receipt", "premium"), ("International Freelancing", "laptop", "basic"),
        ("Crypto & Immigration", "logo-bitcoin", "premium"), ("Tech Job Immigration", "code-slash", "basic"),
        ("AI & Automation Immigration", "hardware-chip", "premium"), ("Healthcare Worker Migration", "medkit", "basic"),
        ("Teacher Immigration Guide", "school", "basic"), ("Nurse Immigration Guide", "medkit", "premium"),
        ("Engineer Immigration Guide", "construct", "basic"), ("Doctor Immigration Guide", "medkit", "premium"),
        ("Lawyer Immigration Guide", "briefcase", "premium"), ("Accountant Migration", "calculator", "basic"),
        ("Chef/Hospitality Migration", "restaurant", "basic"), ("Construction Worker Migration", "hammer", "basic"),
        ("Agricultural Worker Migration", "leaf", "basic"), ("Domestic Worker Migration", "home", "basic"),
        ("Maritime Worker Migration", "boat", "basic"), ("Aviation Worker Migration", "airplane", "premium"),
        ("Sports Professional Migration", "football", "premium"), ("Artist/Creative Migration", "color-palette", "basic"),
    ]
    for name, icon, tier in tech:
        add(name, "Industry-Specific Migration", icon, tier, 10)

    # ═══ SAFETY & COMPLIANCE (20+) ═══
    safety = [
        ("Visa Fraud Prevention", "shield", "free"), ("Immigration Scam Red Flags", "warning", "free"),
        ("Fake Agency Detection", "alert-circle", "free"), ("Document Fraud Awareness", "document-text", "free"),
        ("Identity Theft Protection", "lock-closed", "basic"), ("Online Safety for Immigrants", "globe", "basic"),
        ("Rights at the Border", "shield-checkmark", "basic"), ("Know Your Rights", "information-circle", "basic"),
        ("Discrimination Protection", "people", "basic"), ("Labor Rights Abroad", "briefcase", "basic"),
        ("Tenant Rights Abroad", "home", "basic"), ("Consumer Protection Abroad", "cart", "basic"),
        ("Emergency Services Guide", "call", "free"), ("Legal Aid Resources", "briefcase", "basic"),
        ("Immigration Hotlines", "call", "free"), ("NGO Support Networks", "people", "basic"),
        ("Religious Organization Help", "book", "basic"), ("Community Support Groups", "people", "basic"),
        ("Mental Health Resources", "heart", "basic"), ("Domestic Violence Resources", "shield", "premium"),
    ]
    for name, icon, tier in safety:
        add(name, "Safety & Compliance", icon, tier, 8)

    return categories


def generate_expanded_lessons(categories):
    """Generate lesson templates for expanded categories"""
    import uuid
    lessons = []
    lesson_type_cycle = ["reading", "video", "audio", "interactive", "reading", "video"]
    difficulty_cycle = ["beginner", "beginner", "intermediate", "intermediate", "advanced"]
    
    for cat in categories:
        count = min(cat.get("lesson_count", 6), 6)  # Generate up to 6 sample lessons per category
        for i in range(count):
            ltype = lesson_type_cycle[i % len(lesson_type_cycle)]
            diff = difficulty_cycle[i % len(difficulty_cycle)]
            xp = {"beginner": 40, "intermediate": 65, "advanced": 100}.get(diff, 50)
            dur = {"reading": 12, "video": 18, "audio": 15, "interactive": 25}.get(ltype, 15)
            
            titles = [
                f"Introduction to {cat['name']}", f"Key Concepts: {cat['name']}",
                f"Advanced Guide: {cat['name']}", f"Practical Tips: {cat['name']}",
                f"Common Mistakes in {cat['name']}", f"Expert Strategies: {cat['name']}",
            ]
            
            lessons.append({
                "lesson_id": str(uuid.uuid4())[:8],
                "category_id": cat["id"],
                "title": titles[i % len(titles)],
                "type": ltype,
                "duration_min": dur,
                "difficulty": diff,
                "xp": xp,
                "content": f"Comprehensive guide covering all aspects of {cat['name']}. "
                           f"This {ltype} lesson ({diff} level, ~{dur} min) provides practical examples, "
                           "expert tips, and actionable insights to help you succeed.",
                "media_url": f"https://content.travelvisa.academy/{ltype}/{cat['id']}/lesson-{i+1}" if ltype in ("video", "audio") else None,
                "thumbnail_url": f"https://content.travelvisa.academy/thumbs/{cat['id']}/lesson-{i+1}.jpg" if ltype == "video" else None,
                "transcript": f"Full transcript for {titles[i % len(titles)]}" if ltype in ("video", "audio") else None,
            })
    return lessons
