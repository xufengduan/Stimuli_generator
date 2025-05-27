from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name="stimulus-generator",
    version="1.0.0",
    author="Stimulus Generator Team",
    description="A tool for generating experiment stimuli using large language models",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/k860822369/Stimulus-Generator",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "stimulus-generator=stimulus_generator.cli:main",
        ],
    },
    package_data={
        "": ["static/*", "*.html"],
    },
) 