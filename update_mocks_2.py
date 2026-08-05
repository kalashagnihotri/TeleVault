import os

for root, _, files in os.walk('tests'):
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        with open(path, 'r', encoding='utf-8') as file:
            content = file.read()
            
        new_content = content
        
        # Inject standard policy fields to config.faces where it's mocked
        if 'config.faces.minimum_face_size_px =' in new_content and 'config.faces.aggregate_method' not in new_content:
            new_content = new_content.replace(
                'config.faces.minimum_face_size_px =',
                'config.faces.aggregate_method = "top_k_mean"\n    config.faces.aggregate_top_k = 3\n    config.faces.minimum_strong_support = 2\n    config.faces.policy_identity = "mock_policy"\n    config.faces.minimum_face_size_px ='
            )

        if 'mock_config.faces.minimum_face_size_px =' in new_content and 'mock_config.faces.aggregate_method' not in new_content:
            new_content = new_content.replace(
                'mock_config.faces.minimum_face_size_px =',
                'mock_config.faces.aggregate_method = "top_k_mean"\n    mock_config.faces.aggregate_top_k = 3\n    mock_config.faces.minimum_strong_support = 2\n    mock_config.faces.policy_identity = "mock_policy"\n    mock_config.faces.minimum_face_size_px ='
            )
            
        if 'args.aggregate_top_k = MagicMock()' in new_content:
            new_content = new_content.replace('args.aggregate_top_k = MagicMock()', 'args.aggregate_top_k = 3')
            
        if new_content != content:
            with open(path, 'w', encoding='utf-8') as out:
                out.write(new_content)
            print(f'Updated {path}')
