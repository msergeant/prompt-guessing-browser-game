# prompt guessing browser game

Multi-player game where players try to guess what prompt was used to generate the image. Players get points based on
their ability to figure out the right prompt or to fool the other players into guessing their prompt.

This is a fork of a private repo that runs the game at frogsandwich.io. It has most of the features from the private
repo but some of the branding images have been altered.

## Installation

To get the project running locally, you'll need to install [mise](https://mise.jdx.dev/getting-started.html).

Once mise is installed, there are only two steps you'll need to do to get the code running locally.


### Step 1

```
> script/setup
```

This will install all the necessary components including python, node, and redis. It will create a virtual python
environment and install all the dependencies. It will initialize a sqlite database and create some initial image data
to start running games.


### Step 2

```
> script/server
```

This will start redis, celery, tailwind, and the django server. If everything is successful, you'll be able to play the game
by navigating to localhost:8000 in your browser.


These scripts were tested on a Linux laptop. You may find that other operating systems do not work as well. To see the
steps that are being run, look inside the `script` folder.


## Playing and testing

When testing locally, you can use 2 browsers or if you just want to see the individual pages, you can navigate to
`localhost:8000/games/dev_pages`

To run the tests do:

`python manage.py test`
