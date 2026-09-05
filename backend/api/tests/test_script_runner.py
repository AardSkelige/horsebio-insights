"""
Тесты запуска проверок: замок, код выхода, предел времени.

Проверяются на скрипте-заглушке во временном каталоге: настоящие проверки
ходят в МойСклад и маркетплейсы.
"""
import os
import sys
import time
import textwrap
import tempfile
import subprocess
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.services import script_runner


def _stub(directory, body):
    path = os.path.join(directory, 'stub_script.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(textwrap.dedent(body))
    return path


def _registry(path, **extra):
    return {'stub': {'id': 'stub', 'name': 'Заглушка', 'script': path, 'args': [], **extra}}


class ExecuteTests(SimpleTestCase):
    def test_finished_run_leaves_exit_code_and_frees_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, """
                import sys
                print('поехали')
                sys.exit(3)
            """)
            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                code = script_runner.execute('stub', run_id='2026-09-05_10-00-00')

            log_file = os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')
            self.assertEqual(code, 3)
            self.assertIn('поехали', open(log_file, encoding='utf-8').read())
            self.assertEqual(open(log_file + '.exit').read(), '3')
            # Замок снят — следующий прогон не будет считать себя лишним.
            self.assertFalse(os.path.exists(os.path.join(tmp, 'stub.pid')))

    def test_second_run_is_skipped_while_the_first_is_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, "print('не должен был запуститься')\n")
            alive = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                    f.write(str(alive.pid))
                with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                        patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                    code = script_runner.execute('stub', run_id='2026-09-05_10-00-00')
            finally:
                alive.kill()
                alive.wait()

            # Пропуск — не ошибка: иначе каждый тик пятиминутной задачи
            # поднимал бы тревогу, пока идёт долгий прогон.
            self.assertEqual(code, script_runner.EXIT_BUSY)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')))

    def test_stale_lock_does_not_block_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, "print('прогон пошёл')\n")
            dead = subprocess.Popen([sys.executable, '-c', 'pass'])
            dead.wait()
            with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                f.write(str(dead.pid))

            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                code = script_runner.execute('stub', run_id='2026-09-05_10-00-00')

            self.assertEqual(code, 0)

    def test_run_over_the_limit_is_killed_and_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, "import time; time.sleep(60)\n")
            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                code = script_runner.execute('stub', run_id='2026-09-05_10-00-00', timeout=1)

            log_file = os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')
            self.assertEqual(code, script_runner.EXIT_TIMEOUT)
            self.assertIn('СНЯТ ПО СРОКУ', open(log_file, encoding='utf-8').read())
            self.assertEqual(open(log_file + '.exit').read(), '124')

    def test_structured_script_gets_results_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, """
                import sys
                print(' '.join(sys.argv[1:]))
            """)
            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path, structured=True)):
                script_runner.execute('stub', run_id='2026-09-05_10-00-00')

            log = open(os.path.join(tmp, 'stub_2026-09-05_10-00-00.log'), encoding='utf-8').read()
            self.assertIn('--results-out', log)
            self.assertIn('stub_2026-09-05_10-00-00.results.json', log)

    def test_unknown_script_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(SCRIPTS_LOGS_DIR=tmp):
                self.assertEqual(script_runner.execute('нет-такого'), script_runner.EXIT_UNKNOWN)


class LaunchTests(SimpleTestCase):
    """Запуск из интерфейса: страница обращается к логу сразу после ответа,
    поэтому и лог, и замок должны появиться до того, как команда поднимется."""

    def test_log_and_lock_appear_before_the_command_starts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner.subprocess, 'Popen') as popen:
                popen.return_value.pid = 4242
                run_id = script_runner.launch('horsebio_backup')

            argv = popen.call_args[0][0]
            self.assertIn('run_check', argv)
            self.assertIn('horsebio_backup', argv)
            self.assertEqual(argv[argv.index('--run-id') + 1], run_id)
            self.assertTrue(os.path.exists(os.path.join(tmp, f'horsebio_backup_{run_id}.log')))
            self.assertEqual(open(os.path.join(tmp, 'horsebio_backup.pid')).read(), '4242')

    def test_command_recognises_the_lock_written_for_it(self):
        """pid, записанный кнопкой, — это pid самой команды, и она не должна
        принять его за чужой прогон."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, "print('прогон пошёл')\n")
            with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                f.write(str(os.getpid()))

            with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                    patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                code = script_runner.execute('stub', run_id='2026-09-05_10-00-00')

            self.assertEqual(code, 0)


class StopTests(SimpleTestCase):
    """Остановка одна на обе страницы, и она обязана оставить след:
    прогон без кода выхода выглядел бы на странице удачным."""

    def _spawn(self, code):
        return subprocess.Popen([sys.executable, '-c', code], start_new_session=True)

    def test_nothing_to_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(SCRIPTS_LOGS_DIR=tmp):
                self.assertEqual(script_runner.stop('stub'), script_runner.STOP_IDLE)

    def test_stale_lock_is_swept(self):
        with tempfile.TemporaryDirectory() as tmp:
            dead = self._spawn('pass')
            dead.wait()
            with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                f.write(str(dead.pid))

            with override_settings(SCRIPTS_LOGS_DIR=tmp):
                self.assertEqual(script_runner.stop('stub'), script_runner.STOP_GONE)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'stub.pid')))

    def test_running_process_gets_a_term(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = os.path.join(tmp, 'stub.pid')
            # Ведёт себя как run_check: по сигналу дописывает итог и снимает
            # замок. Именно снятый замок, а не смерть процесса, и означает
            # конец прогона — процесс успевает побыть зомби.
            ready = os.path.join(tmp, 'ready')
            alive = self._spawn(
                'import signal, os, sys, time\n'
                f'pid_path = {pid_path!r}\n'
                'signal.signal(signal.SIGTERM, lambda *a: (os.unlink(pid_path), sys.exit(0)))\n'
                f'open({ready!r}, "w").close()\n'
                'time.sleep(30)\n'
            )
            with open(pid_path, 'w') as f:
                f.write(str(alive.pid))
            # Сигнал, пришедший до установки обработчика, убил бы процесс
            # по умолчанию — дожидаемся готовности.
            for _ in range(100):
                if os.path.exists(ready):
                    break
                time.sleep(0.05)
            try:
                with override_settings(SCRIPTS_LOGS_DIR=tmp):
                    outcome = script_runner.stop('stub')
            finally:
                alive.kill()
                alive.wait()

            self.assertEqual(outcome, script_runner.STOP_STOPPED)

    def test_deaf_process_is_killed_and_the_run_is_marked(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('прогон шёл\n')
            deaf = self._spawn(
                'import signal, time\n'
                'signal.signal(signal.SIGTERM, lambda *a: None)\n'
                'time.sleep(30)\n'
            )
            with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                f.write(str(deaf.pid))
            try:
                with override_settings(SCRIPTS_LOGS_DIR=tmp):
                    outcome = script_runner.stop('stub', grace_sec=0.5)
            finally:
                deaf.kill()
                deaf.wait()

            self.assertEqual(outcome, script_runner.STOP_KILLED)
            self.assertEqual(open(log_file + '.exit').read(), '-9')
            self.assertIn('ОСТАНОВЛЕН', open(log_file, encoding='utf-8').read())


class LockTests(SimpleTestCase):
    """Замок лежит в томе и переживает пересоздание контейнера, а номера
    процессов в новом контейнере начинаются заново."""

    def test_reused_pid_does_not_count_as_a_running_check(self):
        if script_runner._proc_start_time(os.getpid()) is None:
            self.skipTest('нет /proc — проверка момента запуска недоступна')

        with tempfile.TemporaryDirectory() as tmp:
            # Живой процесс, но замок помнит другой момент запуска: значит
            # номер достался чужому процессу после пересоздания контейнера.
            alive = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                    f.write(f'{alive.pid} 1')
                with override_settings(SCRIPTS_LOGS_DIR=tmp):
                    self.assertFalse(script_runner.is_running('stub'))
            finally:
                alive.kill()
                alive.wait()

    def test_lock_is_not_taken_from_a_living_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            alive = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with override_settings(SCRIPTS_LOGS_DIR=tmp):
                    self.assertTrue(script_runner._claim_lock('stub', alive.pid))
                    self.assertFalse(script_runner._claim_lock('stub', os.getpid()))
            finally:
                alive.kill()
                alive.wait()

    def test_skipped_run_marks_the_log_prepared_for_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _stub(tmp, "print('не должен был запуститься')\n")
            log_file = os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')
            open(log_file, 'w').close()
            alive = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                    f.write(str(alive.pid))
                with override_settings(SCRIPTS_LOGS_DIR=tmp), \
                        patch.object(script_runner, 'SCRIPTS_BY_ID', _registry(path)):
                    code = script_runner.execute('stub', run_id='2026-09-05_10-00-00')
            finally:
                alive.kill()
                alive.wait()

            self.assertEqual(code, script_runner.EXIT_BUSY)
            self.assertEqual(open(log_file + '.exit').read(), '75')


class SignalTests(SimpleTestCase):
    def test_own_process_group_is_never_signalled(self):
        """killpg по своей группе снёс бы веб-процесс целиком. Так бывает,
        когда лидер группы не виден в нашем пространстве имён и getpgid
        возвращает ноль."""
        with patch.object(script_runner.os, 'getpgid', return_value=0), \
                patch.object(script_runner.os, 'killpg') as killpg, \
                patch.object(script_runner.os, 'kill') as kill:
            script_runner._signal_pid(4242, 15)

        killpg.assert_not_called()
        kill.assert_called_once_with(4242, 15)

    def test_orphaned_script_is_killed_with_the_command(self):
        """Скрипт живёт в своей группе: убить только run_check значит оставить
        его работать — и через пять минут он встретится со своим же запуском."""
        with tempfile.TemporaryDirectory() as tmp:
            def deaf(marker):
                # Сигнал, пришедший до установки обработчика, убил бы процесс
                # по умолчанию — отмечаем готовность файлом.
                return (
                    'import signal, time\n'
                    'signal.signal(signal.SIGTERM, lambda *a: None)\n'
                    f'open({marker!r}, "w").close()\n'
                    'time.sleep(30)\n'
                )

            owner_ready = os.path.join(tmp, 'owner-ready')
            script_ready = os.path.join(tmp, 'script-ready')
            owner = subprocess.Popen([sys.executable, '-c', deaf(owner_ready)], start_new_session=True)
            script = subprocess.Popen([sys.executable, '-c', deaf(script_ready)], start_new_session=True)
            try:
                for _ in range(100):
                    if os.path.exists(owner_ready) and os.path.exists(script_ready):
                        break
                    time.sleep(0.05)
                with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                    f.write(str(owner.pid))
                with open(os.path.join(tmp, 'stub.script.pid'), 'w') as f:
                    f.write(str(script.pid))
                with override_settings(SCRIPTS_LOGS_DIR=tmp):
                    outcome = script_runner.stop('stub', grace_sec=0.5)
                for _ in range(50):
                    if owner.poll() is not None and script.poll() is not None:
                        break
                    time.sleep(0.1)
            finally:
                owner.kill(); owner.wait()
                script.kill(); script.wait()

            self.assertEqual(outcome, script_runner.STOP_KILLED)
            self.assertEqual(script.returncode, -9)
            self.assertFalse(os.path.exists(os.path.join(tmp, 'stub.script.pid')))

    def test_run_that_died_without_finishing_is_marked(self):
        """Прогон без кода выхода страница считает удачным — оборванный
        обязан оставить след."""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, 'stub_2026-09-05_10-00-00.log')
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('прогон шёл\n')
            dead = subprocess.Popen([sys.executable, '-c', 'pass'])
            dead.wait()
            with open(os.path.join(tmp, 'stub.pid'), 'w') as f:
                f.write(str(dead.pid))

            with override_settings(SCRIPTS_LOGS_DIR=tmp):
                outcome = script_runner.stop('stub')

            self.assertEqual(outcome, script_runner.STOP_GONE)
            self.assertEqual(open(log_file + '.exit').read(), '-9')
            self.assertIn('не записав итог', open(log_file, encoding='utf-8').read())
