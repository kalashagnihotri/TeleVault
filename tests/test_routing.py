from src.routing import RouteInput, choose_topic

def test_routing_precedence_screenshot_over_no_gps():
    # screenshot + no GPS -> screenshots_documents (NOT misc)
    data = RouteInput("image", (), ("screenshot", "indoor"), False)
    assert choose_topic(data) == "screenshots_documents"

def test_routing_precedence_one_known_over_screenshot():
    # screenshot + one known person + no GPS -> people
    data = RouteInput("image", ("Person One",), ("screenshot",), False)
    assert choose_topic(data) == "people"

def test_routing_precedence_two_known_over_screenshot():
    # screenshot + 2+ known people + no GPS -> family_groups
    data = RouteInput("image", ("Person One", "Person Two"), ("screenshot",), False)
    assert choose_topic(data) == "family_groups"

def test_unknown_person_does_not_route_to_people():
    # screenshot + unknown/no face + no GPS -> screenshots_documents
    data = RouteInput("image", ("Unknown Person",), ("screenshot",), False)
    assert choose_topic(data) == "screenshots_documents"
    
def test_mixed_face_results_routing():
    # one known + one unknown -> people
    data = RouteInput("image", ("Person One", "Unknown Person"), ("screenshot",), True)
    assert choose_topic(data) == "people"

    # two known + unknown -> family_groups
    data = RouteInput("image", ("Person One", "Person Two", "Unknown Person"), ("screenshot",), True)
    assert choose_topic(data) == "family_groups"

def test_existing_non_face_routing_cases() -> None:
    # no GPS (without screenshot/people) -> misc
    assert choose_topic(RouteInput("image", (), (), False)) == "misc"
    
    # document
    assert choose_topic(RouteInput("image", (), ("document",), True)) == "screenshots_documents"
    
    # travel
    assert choose_topic(RouteInput("image", (), ("travel",), True)) == "travel_nature"
    
    # video
    assert choose_topic(RouteInput("video", (), (), True)) == "videos"
    
    # everyday
    assert choose_topic(RouteInput("image", (), (), True)) == "everyday"
