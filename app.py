"""CareQuanta entrypoint: one process, env-driven config, no interactive setup."""

from clinic import create_app

app = create_app()


if __name__ == "__main__":
    # use_reloader=False keeps a single process for the documented start command.
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=False,
        use_reloader=False,
    )
