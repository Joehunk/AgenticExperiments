def match_test(data):
    match data:
        case {'type': 'event_callback', 'event': {'type': 'message'} as event}:
            return f"Message event: {event}"
        case _:
            return "No match"
        
print(match_test({'type': 'event_callback', 'event': {'type': 'message', 'text': 'Hello'}}))