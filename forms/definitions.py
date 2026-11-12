"""Static definitions for the application forms."""

event_nature_options = [
    {'value': 'hackathon', 'label': 'Hackathon/ Coding'},
    {'value': 'workshop', 'label': 'Workshop/ Seminar/ Webinar/ Symposium'},
    {'value': 'dance', 'label': 'Dance'},
    {'value': 'singing', 'label': 'Singing'},
    {'value': 'blood_donor', 'label': 'Blood Donation'},
    {'value': 'other', 'label': 'Other'}
]

# Form Fields Defined
FORM_DEFINITIONS = {
    'part_in_comp': {
        'title': 'Participation in Competition/Contest/ Activity',
        'description': [
            "Certificate of participation for Cultural/ Technical (e.g. Hackathon)/ Sports/ Non-Technical events in any Competition/ Contest/ Activity organized by SKIT or any other Institute.",
            "It should be a participation certificate for a competition/ contest or some significant events",
            "Event should be organized by SKIT or any other institute and you should represent SKIT.",
            "Personal level participation certificate NOT allowed. Only participation in an activity as an SKIT student is valid.",
            "Participation certificate should mention your name as student of SKIT. for e.g. Ajay Gupta of SKIT participated in xyz event.",
            "Certificate of completion (For e.g successfully completed an online assesment/ course/ training etc) is NOT allowed. Certificate for Appearing in or Clearing an online assesment/ test is NOT allowed."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                ]
            },
            {
                'field_label': 'Name of the Competition/Event/Activity',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True, 
                'placeholder': 'e.g : SUR, Mayukh, Kill With Fire, Game of Quizzes, Mahatma Gandhi Quiz',
                'help_text': 'Exactly as Mentioned in the Certificate',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 50
                }
            },
            {
                'field_label': 'Team/Individual',
                'field_type': 'select',
                'field_name': 'participation_type',
                'required': True,
                'options': [
                    {'value': 'team', 'label': 'Team'},
                    {'value': 'individual', 'label': 'Individual'},
                ]
            },
            {
                'field_label': 'Event Category',
                'field_type': 'select',
                'field_name': 'event_category',
                'required': True,
                'options': [
                    {'value': 'cultural', 'label': 'Cultural'},
                    {'value': 'technical', 'label': 'Technical'},
                    {'value': 'sports', 'label': 'Sports'},
                    {'value': 'non-technical', 'label': 'Non-Technical'},
                ]
            },
            {
                'field_label': 'Nature of the Event',
                'field_type': 'select',
                'field_name': 'event_nature',
                'required': True,
                'options': event_nature_options
            },
            {
                'field_label': 'Event Level',
                'field_type': 'select',
                'field_name': 'event_level',
                'required': True,
                'help_text': '<b>College Level:</b> Event within SKIT only.<br><b>University Level:</b> Only RTU affiliated college participated.<br><b>State Level:</b> Different colleges/universities all over Rajasthan participated.<br><b>National Level:</b> Colleges/Universities outside Rajasthan participated.<br><b>International Level:</b> Colleges/Universities outside India participated.',
                'options': [
                    {'value': 'college', 'label': 'College'},
                    {'value': 'university', 'label': 'University'},
                    {'value': 'state', 'label': 'State'},
                    {'value': 'national', 'label': 'National'},
                    {'value': 'international', 'label': 'International'},
                ]
            },
            {
                'field_label': 'Event Type',
                'field_type': 'select',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'intra_college', 'label': 'Intra College'},
                    {'value': 'inter_college', 'label': 'Inter College'},
                ]
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'select',
                'field_name': 'event_mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'},
                    {'value': 'blended', 'label': 'Blended'},
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'help_text': 'Start date of the event',
                'field_validation': {
                    'max_date': 'today'
                }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'help_text': 'End date of the event',
                'field_validation': {
                    'max_date': 'today',
                    'after_field': 'from_date'
                }
            },
            {
                'field_label': 'Organizer',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,
                'placeholder': 'e.g. SKIT, Jaipur',
                'help_text': 'Organization that conducted the event',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 150
                }
            },
            {
                'field_label': 'Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g. Civil block, SKIT, Jaipur',
                'help_text': 'Location where the event took place. Write "Online Activity" if event mode was online',
                'field_validation': {
                    'min_length': 3,
                    'max_length': 200
                }
            },
            {
                'field_label': 'Certificate/Proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Upload your participation certificate or equivalent proof',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },

    'winner_achievement': {
        'title': 'Winner/Award/ Other Achievement',
        'description':[
            'Winner/ Runner Up/ Consolation/ Good Rank or Position/ Award/ Prize in some high level Cultural/ Technical(e.g. Hackathon)/ Sports/ Non-Technical competition/ contest organized by SKIT or any other Institute/ University/ Organization.',
            'For e.g. Winner in Inter College Singing Competition/ Hackathon Runner Up/ 3rd Position in quiz competition/ 450 Rank in international level coding test such as Google Code Jam/ Player of the tournament award in state level cricket league etc',
            'Certificate should mention some Rank/ Place/ Position in a competition or some high level achievement like man of the match/ player of the tournament etc.',
            'Non-Competition certificates for e.g. Certificate of clearing some exam/ test/ assessment (with some score) but without a rank/ position/ place is NOT allowed. It should be a certificate for only a "Competition/ Contest" activity.'
            ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': True,
                'placeholder': 'Write NA if position already mentioned',
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize (if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': True,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact, Email Id & Address of Institution/Organization(Event Organizer)',
                'field_type': 'text',
                'field_name': 'organizer_details',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur, info@skit.ac.in, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Competition/Event/Activity',
                'field_type': 'text',
                'field_name': 'event_title',
                'required': True,
                'placeholder': 'e.g., Google Code Jam, Smart India Hackathon',
                'help_text': 'Exactly as Mentioned in the Certificate.',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Event Category',
                'field_type': 'select',
                'field_name': 'event_category',
                'required': True,
                'options': [
                    {'value': 'cultural', 'label': 'Cultural'},
                    {'value': 'technical', 'label': 'Technical'},
                    {'value': 'sports', 'label': 'Sports'},
                    {'value': 'non-technical', 'label': 'Non-Technical'},
                ]
            },
            {
                'field_label': 'Nature of the Event',
                'field_type': 'select',
                'field_name': 'event_nature',
                'required': True,
                'options': event_nature_options
            },
            {
                'field_label': 'Event Level',
                'field_type': 'select',
                'field_name': 'event_level',
                'required': True,
                'help_text': '<b>College Level:</b> Event within SKIT only.<br><b>University Level:</b> Only RTU affiliated college participated.<br><b>State Level:</b> Different colleges/universities all over Rajasthan participated.<br><b>National Level:</b> Colleges/Universities outside Rajasthan participated.<br><b>International Level:</b> Colleges/Universities outside India participated.',
                'options': [
                    {'value': 'college', 'label': 'College'},
                    {'value': 'university', 'label': 'University'},
                    {'value': 'state', 'label': 'State'},
                    {'value': 'national', 'label': 'National'},
                    {'value': 'international', 'label': 'International'},
                ]
            },
            {
                'field_label': 'Event Type',
                'field_type': 'select',
                'field_name': 'event_type',
                'required': True,
                'options': [
                    {'value': 'intra_college', 'label': 'Intra College'},
                    {'value': 'inter_college', 'label': 'Inter College'},
                ]
            },
            {
                'field_label': 'Team/Individual',
                'field_type': 'select',
                'field_name': 'team_individual',
                'required': True,
                'options': [
                    {'value': 'individual', 'label': 'Individual'},
                    {'value': 'team', 'label': 'Team'}
                ]
            },
            {
                'field_label': 'Name of the team',
                'field_type': 'text',
                'field_name': 'team_name',
                'required': False,
                'depends_on': {
                    'field': 'team_individual',
                    'value': 'team'
                },
                'required_if_visible': True,
                'field_validation': { 'max_length': 100 }
            },
            {
                'field_label': 'Name of all team members',
                'field_type': 'text',
                'field_name': 'team_members',
                'required': False,
                'depends_on': {
                    'field': 'team_individual',
                    'value': 'team'
                },
                'required_if_visible': True,
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Mode of Event',
                'field_type': 'select',
                'field_name': 'event_mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'},
                    {'value': 'blended', 'label': 'Blended'},
                ]
            },
            {
                'field_label': 'Event Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur / Write online if online',
                'field_validation': { 'min_length': 3, 'max_length': 200 }
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 
                    'max_date': 'today',                     
                    'after_field': 'from_date'  # Must be after from_date
                }
            },
            {
                'field_label': 'Award Certificate/other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': { 'accepted_types': '.pdf', 'max_size': '5MB' }
            }
        ]
    },

    'online_course': {
        'title': 'Coursera / edX Certification',
        'description': [
            "Only Upload Coursera/edX Certificates. Course certificates from other platforms such as Udemy are NOT allowed."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title(not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'position',
                    'value': 'other'
                },
                'required_if_visible': True,
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given(Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize(if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of the Course',
                'field_type': 'text',
                'field_name': 'course_name',
                'required': True,
                'placeholder': 'e.g., Python for Everybody',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Platform',
                'field_type': 'text',
                'field_name': 'platform',
                'required': True,
                'placeholder': 'e.g., Coursera, edX, Udemy',
                'field_validation': { 'max_length': 100 }
            },
            {
                'field_label': 'Date of Completion',
                'field_type': 'date',
                'field_name': 'completion_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },
    
    'internship_stipend': {
        'title': 'Internship/Training (Only with Stipend) before Placement',
        'description': [
            'Submit details for a paid internship or training that occurred before any final job placement.'
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                ]
            },
            {
                'field_label': 'Name of the Company',
                'field_type': 'text',
                'field_name': 'company_name',
                'required': True,
                'placeholder': 'e.g., Google, Microsoft, Amazon',
                'help_text': 'The internship/training should be done before the student is placed in a company and got stipend.',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Job Role Offered',
                'field_type': 'text',
                'field_name': 'job_role',
                'required': True,
                'placeholder': 'e.g. Software Engineer I',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Stipend Amount',
                'field_type': 'number',
                'field_name': 'stipend_amount',
                'required': True,
                'placeholder': 'e.g. 5000',
                'help_text': 'Enter the numeric value of the stipend in Rs. Do NOT include commas or currency symbols.',
                'field_validation': { 'min': 1 }
            },
            {
                'field_label': 'Stipend Amount Received',
                'field_type': 'radio',
                'field_name': 'stipend_frequency',
                'required': True,
                'options': [
                    {'value': 'per_month', 'label': 'Per Month'},
                    {'value': 'lump_sum', 'label': 'Lump Sum'}
                ]
            },
            {
                'field_label': 'Location/Address',
                'field_type': 'text',
                'field_name': 'location',
                'required': True,
                'placeholder': 'e.g., Bengaluru, Karnataka. Write "Online" if mode was online',
                'field_validation': { 'min_length': 5, 'max_length': 300 }
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 'max_date': 'today', 'after_field': 'from_date' }
            },
            {
                'field_label': 'Mode',
                'field_type': 'select',
                'field_name': 'mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'},
                    {'value': 'blended', 'label': 'Blended'}
                ]
            },
            {
                'field_label': 'Received Offer through',
                'field_type': 'select',
                'field_name': 'offer_through',
                'required': True,
                'options': [
                    {'value': 'college', 'label': 'College'},
                    {'value': 'self', 'label': 'Self'},
                ]
            },
            {
                'field_label': 'Internship/Training Certificate /other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': '''Certificate must contain proof of stipend. If not, merge proof (bank statement, offer letter) into the PDF.
                Max Size: 10MB''',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '10MB'
                }
            }
        ]
    },

    'paper_presented': {
        'title': 'Paper Presented in Conference',
        'description': [
            "Presented paper in any conference (National/International) at SKIT or outside SKIT",
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'participation', 'label': 'Participation'},
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Position/Place/Rank',
                'field_type': 'select',
                'field_name': 'position',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'I', 'label': 'I'},
                    {'value': 'II', 'label': 'II'},
                    {'value': 'III', 'label': 'III'},
                    {'value': 'consolation', 'label': 'Consolation'},
                    {'value': 'other', 'label': 'Other Position/Rank/Title'}
                ]
            },
            {
                'field_label': 'Other Position/Rank/Title (not mentioned in above list)',
                'field_type': 'text',
                'field_name': 'other_position_details',
                'required': False,
                'depends_on': {
                    'field': 'position',
                    'value': 'other'
                },
                'required_if_visible': True,
                'help_text': 'e.g., 28th Rank in National Level Coding Test',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Award Given (Other than Certificate)',
                'field_type': 'select',
                'field_name': 'award_type',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'options': [
                    {'value': 'medal', 'label': 'Medal'},
                    {'value': 'trophy', 'label': 'Trophy'},
                    {'value': 'cash_prize', 'label': 'Cash Prize'},
                    {'value': 'scholarship', 'label': 'Scholarship'},
                    {'value': 'other', 'label': 'Other Prize'},
                    {'value': 'none', 'label': 'None'}
                ]
            },
            {
                'field_label': 'Cash Prize/Other Prize(if any)',
                'field_type': 'text',
                'field_name': 'prize_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': False,
                'placeholder': 'e.g., Cash Prize of 2000 Rs / T-Shirt',
                'help_text': 'Write NA if no prize',
                'field_validation': {'max_length': 150}
            },
            {
                'field_label': 'Date of Receiving Award/Certificate',
                'field_type': 'date',
                'field_name': 'award_date',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Name, Contact Email Id & Address of Agency/Body/Organization Giving Award',
                'field_type': 'text',
                'field_name': 'award_agency_details',
                'required': False,
                'depends_on': {
                    'field': 'certification_type',
                    'value': 'achievement'
                },
                'required_if_visible': True,
                'placeholder': 'e.g., HDFC Bank, Malviya Nagar Branch, ...',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Name of Conference',
                'field_type': 'text',
                'field_name': 'conference_name',
                'required': True,
                'placeholder': 'e.g., 3rd International Conference on Internet of Things...',
                'field_validation': { 'max_length': 200 }
            },
            {
                'field_label': 'National/International',
                'field_type': 'select',
                'field_name': 'conference_level',
                'required': True,
                'options': [
                    {'value': 'national', 'label': 'National'},
                    {'value': 'international', 'label': 'International'}
                ]
            },
            {
                'field_label': 'From Date',
                'field_type': 'date',
                'field_name': 'from_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'To Date',
                'field_type': 'date',
                'field_name': 'to_date',
                'required': True,
                'field_validation': { 'max_date': 'today', 'after_field': 'from_date' }
            },
            {
                'field_label': 'Paper Title',
                'field_type': 'text',
                'field_name': 'paper_title',
                'required': True,
                'placeholder': 'Enter the full title of your paper',
                'field_validation': { 'max_length': 250 }
            },
            {
                'field_label': 'Other Authors (Name, Branch)',
                'field_type': 'text',
                'field_name': 'other_authors',
                'required': True,
                'placeholder': 'e.g., 1. Ajay Sharma, CSE 2. Abhay Kumar, CSE.',
                'field_validation': { 'max_length': 500 }
            },
            {
                'field_label': 'Mode of Conference',
                'field_type': 'select',
                'field_name': 'mode',
                'required': True,
                'options': [
                    {'value': 'online', 'label': 'Online'},
                    {'value': 'offline', 'label': 'Offline'},
                    {'value': 'blended', 'label': 'Blended'}
                ]
            },
            {
                'field_label': 'Organizer',
                'field_type': 'text',
                'field_name': 'organizer',
                'required': True,
                'placeholder': 'e.g., IEEE, Springer, SKIT Jaipur',
                'field_validation': { 'max_length': 150 }
            },
            {
                'field_label': 'Event Venue',
                'field_type': 'text',
                'field_name': 'venue',
                'required': True,
                'placeholder': 'e.g., SKIT Jaipur / Write online if online',
                'field_validation': { 'min_length': 3, 'max_length': 200 }
            },
            {
                'field_label': 'Conference Paper Presented Certificate/other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Proof for paper presentation is mandatory. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    },

    'financial_grant': {
        'title': 'Financial Grant Received',
        'description': [
            "Received any financial funding for project/start up/DST project etc. from private/government agency."
        ],
        'enctype': 'multipart/form-data',
        'fields': [
            {
                'field_label': 'Certification Type',
                'field_type': 'select',
                'field_name': 'certification_type',
                'required': True,
                'options': [
                    {'value': 'achievement', 'label': 'Achievement'}
                ]
            },
            {
                'field_label': 'Funding Agency Name',
                'field_type': 'text',
                'field_name': 'agency_name',
                'required': True,
                'placeholder': 'e.g., Department of Science & Technology, Govt. of India',
                'field_validation': { 'max_length': 200 }
            },
            {
                'field_label': 'Funded Amount',
                'field_type': 'number',
                'field_name': 'funded_amount',
                'required': True,
                'placeholder': 'Enter the amount in Rs.',
                'field_validation': { 'min': 1 }
            },
            {
                'field_label': 'Funded For',
                'field_type': 'text',
                'field_name': 'funded_for',
                'required': True,
                'placeholder': 'e.g., Research Project, Startup Idea, Conference Travel',
                'field_validation': { 'max_length': 250 }
            },
            {
                'field_label': 'Status of Funding Agency',
                'field_type': 'radio',
                'field_name': 'agency_status',
                'required': True,
                'options': [
                    {'value': 'private', 'label': 'Private'},
                    {'value': 'government', 'label': 'Government'}
                ]
            },
            {
                'field_label': 'Funding Date',
                'field_type': 'date',
                'field_name': 'funding_date',
                'required': True,
                'field_validation': { 'max_date': 'today' }
            },
            {
                'field_label': 'Financial Grant Certificate/ other proof',
                'field_type': 'file',
                'field_name': 'certificate',
                'required': True,
                'help_text': 'Only PDF file format is acceptable. Max Size: 5MB',
                'validation': {
                    'accepted_types': '.pdf',
                    'max_size': '5MB'
                }
            }
        ]
    }
}

