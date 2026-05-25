pip install -r requirements.txt
python create_sample_photos.py --out test_photos
python organize_photos.py --dir test_photos --dry-run --no-ai --verbose
python organize_photos.py --dir test_photos --no-ai --verbose