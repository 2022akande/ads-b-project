"""Train the LightGBM baseline detector (TDD §4.1, M2 milestone).

Run from the backend/ directory so `app` and `ml` import cleanly:

    cd backend
    python -m ml.train

Produces ml/model.joblib, which the live Detector auto-loads at startup and
blends with the physics layer (TDD §4.1). Falls back to a scikit-learn
GradientBoosting model if LightGBM is unavailable, so the pipeline always runs.
"""

from __future__ import annotations

import os

import numpy as np

from ml.dataset import build_dataset


def _make_model():
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=300,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            class_weight="balanced",
            random_state=42,
        ), "lightgbm"
    except Exception:
        from sklearn.ensemble import GradientBoostingClassifier

        return GradientBoostingClassifier(random_state=42), "sklearn-gbdt"


def main() -> None:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import (
        average_precision_score,
        classification_report,
        roc_auc_score,
    )
    from sklearn.model_selection import train_test_split

    print("Building dataset from synthetic generator ...")
    X, y, feature_names = build_dataset()
    print(f"  X={X.shape}  positives={int(y.sum())}/{len(y)} ({y.mean():.1%})")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    base, kind = _make_model()
    print(f"Training {kind} baseline ...")
    base.fit(X_train, y_train)

    # Calibrate so `score` reflects a true probability (TDD §4.3).
    model = CalibratedClassifierCV(base, method="isotonic", cv=3)
    model.fit(X_train, y_train)

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    auc = roc_auc_score(y_test, proba)
    ap = average_precision_score(y_test, proba)
    print(f"\nROC-AUC: {auc:.4f}   PR-AUC: {ap:.4f}")
    print(classification_report(y_test, pred, target_names=["legit", "malicious"]))

    out_path = os.path.join(os.path.dirname(__file__), "model.joblib")
    import joblib

    joblib.dump(
        {
            "model": model,
            "meta": {
                "kind": kind,
                "roc_auc": round(float(auc), 4),
                "pr_auc": round(float(ap), 4),
                "feature_names": feature_names,
                "n_train": int(len(y_train)),
            },
        },
        out_path,
    )
    print(f"\nSaved model -> {out_path}")
    print("Restart the backend; the detector will auto-load it (TDD §4.1).")


if __name__ == "__main__":
    main()
