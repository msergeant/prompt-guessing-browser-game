seeds:
	rm -rf media/*
	./manage.py reset_db --noinput
	./manage.py migrate
	./manage.py seed_development_data
