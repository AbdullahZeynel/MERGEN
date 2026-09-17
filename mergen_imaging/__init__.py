"""Isolated live imaging runner; imported only by the model virtualenv."""

# The live path answers as the product configuration, not as one of its members:
# nnU-Net BraTS21 (five folds) and Swin UNETR BraTS21 (fold 0) are combined by
# the UWCSE v3 rule. A manifest that describes anything else is refused.
MODEL_ID = "mergen-uwcse"
MODEL_VERSION = "v3"

# Members in the order they run. Only one is resident at a time: measured peaks
# are 3.1 GiB (nnU-Net) and 4.4 GiB (Swin), sequential, on the 16 GB host.
NNUNET_MEMBER = ("nnunet-brats21", "dataset002-brats19-5fold")
SWIN_MEMBER = ("swin-unetr-brats21", "fold0-f48-ep300")
NNUNET_FOLDS = (0, 1, 2, 3, 4)

# Frozen per-region nnU-Net weights of the product configuration. Fitted on the
# 30 validation cases and read out once on the locked test split; the registry
# file is the source of these numbers and `models/imaging/test_live_product_rule.py`
# fails if the two drift apart.
PRODUCT_WEIGHTS = (0.425, 0.6966666666666669, 0.4466666666666666)
