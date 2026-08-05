import os, re

for root, _, files in os.walk('tests'):
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        with open(path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        new_content = content
        if 'config = MagicMock()' in new_content and 'config.faces.minimum_face_size_px =' in new_content:
            new_content = re.sub(r'config = MagicMock\(\)\n\s+config\.faces\.minimum_face_size_px = (\d+)', 
                r"config = MagicMock()\n    config.faces = MagicMock(minimum_face_size_px=\1, aggregate_method='top_k_mean', aggregate_top_k=3, minimum_strong_support=2, minimum_references_per_person=3, policy_identity='top_k_mean:k=3:mss=2')", new_content)
        elif 'mock_config = MagicMock()' in new_content and 'mock_config.faces.minimum_face_size_px =' in new_content:
            new_content = re.sub(r'mock_config = MagicMock\(\)\n\s+mock_config\.faces\.minimum_face_size_px = (\d+)', 
                r"mock_config = MagicMock()\n    mock_config.faces = MagicMock(minimum_face_size_px=\1, aggregate_method='top_k_mean', aggregate_top_k=3, minimum_strong_support=2, minimum_references_per_person=3, policy_identity='top_k_mean:k=3:mss=2')", new_content)

        # replace snapshot old fields
        new_content = new_content.replace('\"accept_threshold\":', '\"aggregate_accept_threshold\":')
        new_content = new_content.replace('\"review_threshold\":', '\"aggregate_review_threshold\":')
        new_content = new_content.replace('\"minimum_margin\":', '\"minimum_aggregate_margin\":')
        
        if new_content != content:
            with open(path, 'w', encoding='utf-8') as out:
                out.write(new_content)
            print(f'Updated {path}')
