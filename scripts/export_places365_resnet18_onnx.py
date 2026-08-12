import os
import urllib.request
import hashlib
import torch
import torchvision.models as models
from torchvision import transforms
from PIL import Image
import onnxruntime as ort
import numpy as np

def sha256_file(path):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()

def download_file(url, path):
    if not os.path.exists(path):
        print(f"Downloading {url} to {path}...")
        urllib.request.urlretrieve(url, path)
    return sha256_file(path)

def main():
    model_url = 'http://places2.csail.mit.edu/models_places365/resnet18_places365.pth.tar'
    categories_url = 'https://raw.githubusercontent.com/csailvision/places365/master/categories_places365.txt'

    pth_file = "resnet18_places365.pth.tar"
    cat_file = "categories_places365.txt"
    onnx_file = "resnet18_places365.onnx"

    print("Downloading files...")
    pth_sha = download_file(model_url, pth_file)
    cat_sha = download_file(categories_url, cat_file)
    print(f"PyTorch Checkpoint SHA256: {pth_sha}")
    print(f"Categories SHA256: {cat_sha}")

    print("Loading PyTorch model...")
    # NOTE: models.resnet18 is deprecated, replacing with new weights pattern
    model = models.resnet18(num_classes=365)
    checkpoint = torch.load(pth_file, map_location=lambda storage, loc: storage, weights_only=True)
    
    # Strip 'module.' prefix
    state_dict = {k.replace('module.', ''): v for k, v in checkpoint['state_dict'].items()}
    model.load_state_dict(state_dict)
    model.eval()

    print("Exporting to ONNX...")
    dummy_input = torch.randn(1, 3, 224, 224, dtype=torch.float32)
    
    # Try exporting without dynamic_axes since Dynamo crashes on them.
    # Using fallback=True might also help if it's available.
    try:
        torch.onnx.export(
            model,
            dummy_input,
            onnx_file,
            export_params=True,
            opset_version=14,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output'],
            fallback=True
        )
    except TypeError:
        # fallback argument not supported in some PyTorch versions
        torch.onnx.export(
            model,
            dummy_input,
            onnx_file,
            export_params=True,
            opset_version=14,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output']
        )

    print(f"ONNX Model base generated.")
    
    # Merge external data into a single file if it was created
    import onnx
    import os
    data_file = onnx_file + ".data"
    if os.path.exists(data_file):
        print("Merging external data into single ONNX file...")
        onnx_model = onnx.load(onnx_file, load_external_data=True)
        # Default onnx.save writes a single file without external data
        onnx.save(onnx_model, onnx_file)
        os.remove(data_file)
        print("External data merged and deleted.")

    onnx_sha = sha256_file(onnx_file)
    print(f"ONNX Model SHA256: {onnx_sha}")

    print("Validating parity between PyTorch and ONNX...")
    # Create a random image tensor for validation
    test_tensor = torch.randn(1, 3, 224, 224, dtype=torch.float32)
    
    # PyTorch inference
    with torch.no_grad():
        pt_out = model(test_tensor).numpy()
        
    # ONNX inference
    session = ort.InferenceSession(onnx_file, providers=["CPUExecutionProvider"])
    ort_inputs = {session.get_inputs()[0].name: test_tensor.numpy()}
    ort_out = session.run(None, ort_inputs)[0]

    np.testing.assert_allclose(pt_out, ort_out, rtol=1e-03, atol=1e-05)
    print("SUCCESS: PyTorch and ONNX outputs match numerically.")
    
    # Check top-5 match
    pt_top5 = np.argsort(pt_out[0])[-5:][::-1]
    ort_top5 = np.argsort(ort_out[0])[-5:][::-1]
    
    assert np.array_equal(pt_top5, ort_top5), f"Top 5 classes do not match: {pt_top5} vs {ort_top5}"
    print("SUCCESS: Top 5 predictions match exactly.")
    
    print("Model Size:", os.path.getsize(onnx_file), "bytes")

if __name__ == "__main__":
    main()
