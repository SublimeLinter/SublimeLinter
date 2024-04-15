import argparse
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime


def bump(args):
    # Read the manifest file
    with open(args.manifest, 'r') as manifest_file:
        manifest_data = json.load(manifest_file)

    if args.to_version is not None:
        new_version = args.to_version
    else:
        current_version = list(map(int, manifest_data['packages'][0]['releases'][0]['version'].split(".")))
        new_version = ".".join(map(str, (current_version[0] + 1, *current_version[1:])))

    # Update the release version in the packages section
    for package in manifest_data.get('packages', []):
        for release in package.get('releases', []):
            release['version'] = new_version
            release['date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save the updated manifest
    with open(args.manifest, 'w') as manifest_file:
        json.dump(manifest_data, manifest_file, indent=2)

    print(f"Manifest version bumped to {new_version}")


def serve(args):
    print("Running the server, ctrl+c to abort.")
    try:
        command = "python -m http.server 8000"
        subprocess.run(command, cwd=args.dir, shell=True)
    except KeyboardInterrupt:
        print("\nServer terminated by user.")


def pack(args):
    # cwd = os.path.abspath(args.repo)
    target = os.path.abspath(args.file)
    command = ("git", "archive", "--format=zip", "-o", target, "HEAD")
    subprocess.run(command, cwd=args.repo, shell=True)


def main():
    this_directory = Path(__file__).parent
    parser = argparse.ArgumentParser(description="Update and serve local packages.")
    parser.add_argument("--to-version", help="Version to bump to")
    parser.add_argument(
        "--manifest", type=str, default=this_directory / "repo.json", help="Manifest file"
    )
    parser.add_argument(
        "--repo", type=str, default=".", help="Base folder of the repo you want to archive"
    )
    parser.add_argument(
        "dir", nargs="?", default=this_directory, help="Directory to serve"
    )
    parser.add_argument(
        "file", nargs="?", default=this_directory / "sublime_linter.sublime-package", help="Name of the package file"
    )

    subparsers = parser.add_subparsers(title="subcommands", dest="subcommand")

    # Bump subcommand
    bump_parser = subparsers.add_parser("bump", help="Bump version")
    bump_parser.add_argument("--to-version", help="Version to bump to")
    bump_parser.add_argument(
        "--manifest", type=str, default=this_directory / "repo.json", help="Manifest file"
    )

    # Serve subcommand
    serve_parser = subparsers.add_parser("serve", help="Serve directory")
    serve_parser.add_argument(
        "dir", nargs="?", default=this_directory, help="Directory to serve"
    )

    # Archive subcommand
    pack_parser = subparsers.add_parser("pack", help="Create package file")
    pack_parser.add_argument(
        "--repo", type=str, default=".", help="Base folder of the repo you want to archive"
    )
    pack_parser.add_argument(
        "file", nargs="?", default=this_directory / "sublime_linter.sublime-package", help="Name of the package file"
    )

    args = parser.parse_args()

    if args.subcommand == "bump":
        bump(args)
    elif args.subcommand == "serve":
        serve(args)
    elif args.subcommand == "pack":
        pack(args)
    else:
        pack(args)
        bump(args)
        serve(args)


if __name__ == "__main__":
    main()
