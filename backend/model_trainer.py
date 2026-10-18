"""
Train tiny ML models, quantize to INT8, and export weights as JSON.
Used for the hackathon demo.
"""

import torch
import torch.nn as nn
import numpy as np
import json
import os

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def train_xor() -> dict:
    """Train a 2-layer MLP on XOR, quantize to INT8, and export weights as JSON."""
    # Try multiple seeds until convergence (XOR is sensitive to init)
    X = torch.tensor([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=torch.float32)
    y = torch.tensor([[0], [1], [1], [0]], dtype=torch.float32)

    for seed in range(100):
        torch.manual_seed(seed)
        model = nn.Sequential(
            nn.Linear(2, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
            nn.Sigmoid(),
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=0.05)
        criterion = nn.BCELoss()

        for epoch in range(3000):
            optimizer.zero_grad()
            output = model(X)
            loss = criterion(output, y)
            loss.backward()
            optimizer.step()

        with torch.no_grad():
            preds = (model(X) > 0.5).float()
            if (preds == y).all():
                print(f"[XOR] Converged with seed={seed}")
                break
    else:
        raise RuntimeError("XOR failed to converge with any seed")

    # Verify
    with torch.no_grad():
        predictions = model(X)
        predicted_labels = (predictions > 0.5).float()
        accuracy = (predicted_labels == y).float().mean().item()
        print(f"[XOR] Final loss: {loss.item():.6f}")
        print(f"[XOR] Accuracy: {accuracy * 100:.1f}%")
        print(f"[XOR] Predictions: {predictions.squeeze().tolist()}")
        assert accuracy == 1.0, "XOR model did not converge — all 4 outputs must be correct"

    # Quantize to INT8
    weights_dict = {}
    for name, param in model.named_parameters():
        tensor = param.detach().numpy()
        scale = 127.0 / np.max(np.abs(tensor))
        quantized = np.round(tensor * scale).astype(int)
        weights_dict[name] = {
            "values": quantized.tolist(),
            "scale": float(scale),
        }

    # Save
    out_path = os.path.join(CACHE_DIR, "xor_weights.json")
    with open(out_path, "w") as f:
        json.dump(weights_dict, f, indent=2)
    print(f"[XOR] Weights saved to {out_path}")

    return weights_dict


def train_iris() -> dict:
    """Train a small MLP on Iris dataset, quantize to INT8, and export weights as JSON."""
    from sklearn.datasets import load_iris
    from sklearn.preprocessing import StandardScaler

    # Load and preprocess
    iris = load_iris()
    scaler = StandardScaler()
    X_np = scaler.fit_transform(iris.data)
    y_np = iris.target

    X = torch.tensor(X_np, dtype=torch.float32)
    y = torch.tensor(y_np, dtype=torch.long)

    # Define model
    model = nn.Sequential(
        nn.Linear(4, 8),
        nn.ReLU(),
        nn.Linear(8, 3),
    )

    # Training
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(1000):
        optimizer.zero_grad()
        output = model(X)
        loss = criterion(output, y)
        loss.backward()
        optimizer.step()

    # Evaluate
    with torch.no_grad():
        predictions = model(X).argmax(dim=1)
        accuracy = (predictions == y).float().mean().item()
        print(f"[Iris] Accuracy: {accuracy * 100:.1f}%")

    # Quantize to INT8
    weights_dict = {}
    for name, param in model.named_parameters():
        tensor = param.detach().numpy()
        scale = 127.0 / np.max(np.abs(tensor))
        quantized = np.round(tensor * scale).astype(int)
        weights_dict[name] = {
            "values": quantized.tolist(),
            "scale": float(scale),
        }

    # Save
    out_path = os.path.join(CACHE_DIR, "iris_weights.json")
    with open(out_path, "w") as f:
        json.dump(weights_dict, f, indent=2)
    print(f"[Iris] Weights saved to {out_path}")

    return weights_dict


def export_iris_inputs() -> dict:
    """Quantize the standardized Iris samples to INT8 and save them for the golden reference."""
    from sklearn.datasets import load_iris
    from sklearn.preprocessing import StandardScaler

    iris = load_iris()
    X_np = StandardScaler().fit_transform(iris.data)
    scale = 127.0 / np.max(np.abs(X_np))
    quantized = np.clip(np.round(X_np * scale), -127, 127).astype(int)

    inputs_dict = {
        "input_scale": float(scale),
        "inputs": quantized.tolist(),
        "labels": iris.target.astype(int).tolist(),
    }

    out_path = os.path.join(CACHE_DIR, "iris_inputs.json")
    with open(out_path, "w") as f:
        json.dump(inputs_dict, f)
    print(f"[Iris] {len(quantized)} quantized samples saved to {out_path}")

    return inputs_dict


def define_attention_weights() -> dict:
    """Create random INT8 weight matrices for a demo attention layer."""
    np.random.seed(42)

    Wq = np.random.randint(-127, 128, size=(8, 8)).tolist()
    Wk = np.random.randint(-127, 128, size=(8, 8)).tolist()
    Wv = np.random.randint(-127, 128, size=(8, 8)).tolist()

    weights_dict = {
        "Wq": {"values": Wq},
        "Wk": {"values": Wk},
        "Wv": {"values": Wv},
    }

    # Save
    out_path = os.path.join(CACHE_DIR, "attention_weights.json")
    with open(out_path, "w") as f:
        json.dump(weights_dict, f, indent=2)
    print(f"[Attention] Weights saved to {out_path}")

    return weights_dict


if __name__ == "__main__":
    # Ensure cache directory exists
    os.makedirs(CACHE_DIR, exist_ok=True)

    print("=" * 50)
    print("Training XOR model...")
    print("=" * 50)
    xor_weights = train_xor()

    print()
    print("=" * 50)
    print("Training Iris model...")
    print("=" * 50)
    iris_weights = train_iris()
    export_iris_inputs()

    print()
    print("=" * 50)
    print("Generating attention weights...")
    print("=" * 50)
    attn_weights = define_attention_weights()

    # Summary
    print()
    print("=" * 50)
    print("Summary of generated weights:")
    print("=" * 50)
    print(f"  XOR:       {len(xor_weights)} parameter groups")
    print(f"  Iris:      {len(iris_weights)} parameter groups")
    print(f"  Attention: {len(attn_weights)} weight matrices")

    # Verilog preview
    print()
    print("=" * 50)
    print("Verilog localparam preview (XOR, first 10 lines):")
    print("=" * 50)
    from golden import load_network, network_params
    verilog_str = network_params(load_network("xor"))
    for line in verilog_str.split("\n")[:10]:
        print(line)
