# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from pathlib import PurePath
from typing import List, Optional, Type, cast

from lisa.executable import Tool
from lisa.operating_system import CBLMariner, Posix, Ubuntu
from lisa.tools.curl import Curl
from lisa.tools.echo import Echo
from lisa.tools.gcc import Gcc
from lisa.tools.ln import Ln
from lisa.util import UnsupportedDistroException
from lisa.util.process import ExecutableResult


class Cargo(Tool):
    @property
    def command(self) -> str:
        return "cargo"

    @property
    def can_install(self) -> bool:
        return True

    @property
    def dependencies(self) -> List[Type[Tool]]:
        return [Gcc]

    def _install(self) -> bool:
        os = self.node.os
        cargo_source_url = "https://sh.rustup.rs"
        if isinstance(os, CBLMariner) or isinstance(os, Ubuntu):
            self.__install_dependencies()

            # install cargo/rust
            curl = self.node.tools[Curl]
            result = curl.fetch(
                arg="-sSf",
                url=cargo_source_url,
                execute_arg="-s -- -y",
                shell=True,
            )
            result.assert_exit_code()

            echo = self.node.tools[Echo]
            home_dir = echo.run(
                "$HOME",
                shell=True,
                expected_exit_code=0,
                expected_exit_code_failure_message="failure to grab $HOME path",
            ).stdout

            ln = self.node.tools[Ln]
            ln.create_link(
                is_symbolic=True,
                target=f"{home_dir}/.cargo/bin/cargo",
                link="/usr/local/bin/cargo",
            )
        else:
            raise UnsupportedDistroException(os)
        return self._check_exists()

    def __install_dependencies(self) -> None:
        os: Posix = cast(Posix, self.node.os)

        # install prerequisites
        os.install_packages(["build-essential", "cmake"])

        gcc = self.node.tools[Gcc]
        gcc_version_info = gcc.get_version()
        self.node.log.debug(f"Gcc Version: {gcc_version_info}")

        curl = self.node.tools[Curl]
        curl_version_info = curl.get_version()
        self.node.log.debug(f"Curl Version: {curl_version_info}")

    def build(
        self,
        sudo: bool = False,
        cwd: Optional[PurePath] = None,
    ) -> ExecutableResult:
        err_msg = "Cargo build failed"
        echo = self.node.tools[Echo]
        original_path = echo.run(
            "$PATH",
            shell=True,
            expected_exit_code=0,
            expected_exit_code_failure_message="failure to grab $PATH via echo",
        ).stdout
        home_path = echo.run(
            "$HOME",
            shell=True,
            expected_exit_code=0,
            expected_exit_code_failure_message="failure to grab $HOME path",
        ).stdout
        new_path = f"{home_path}/.cargo/bin:{original_path}"
        result = self.run(
            "build",
            expected_exit_code=0,
            expected_exit_code_failure_message=err_msg,
            sudo=sudo,
            cwd=cwd,
            update_envs={"PATH": new_path},
        )
        return result

    def test(
        self,
        sudo: bool = False,
        cwd: Optional[PurePath] = None,
    ) -> ExecutableResult:
        echo = self.node.tools[Echo]
        original_path = echo.run(
            "$PATH",
            shell=True,
            expected_exit_code=0,
            expected_exit_code_failure_message="failure to grab $PATH via echo",
        ).stdout
        home_path = echo.run(
            "$HOME",
            shell=True,
            expected_exit_code=0,
            expected_exit_code_failure_message="failure to grab $HOME path",
        ).stdout
        new_path = f"{home_path}/.cargo/bin:{original_path}"
        result = self.run(
            "test",
            sudo=sudo,
            cwd=cwd,
            update_envs={"PATH": new_path},
        )
        return result
