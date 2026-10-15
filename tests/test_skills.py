import unittest

from agents.skills import SkillDefinition, resolve_skill_prompt


class SkillPromptTests(unittest.TestCase):
    def test_arguments_are_inserted_literally(self):
        skill = SkillDefinition(name='example', description='test',
                                prompt_template='$ARGUMENTS / ${ARGUMENTS}')
        for args in [r'C:\Users\dev\new.py', r'\1 \g<name> \n', '定位这个报错']:
            with self.subTest(args=args):
                self.assertEqual(resolve_skill_prompt(skill, args), f'{args} / {args}')

    def test_inserted_values_are_not_expanded_again(self):
        skill = SkillDefinition(name='example', description='test',
                                prompt_template='$ARGUMENTS | ${CLAUDE_SKILL_DIR}',
                                skill_dir='/tmp/$ARGUMENTS')
        self.assertEqual(resolve_skill_prompt(skill, '${CLAUDE_SKILL_DIR}'),
                         '${CLAUDE_SKILL_DIR} | /tmp/$ARGUMENTS')

    def test_empty_arguments_and_skill_directory(self):
        skill = SkillDefinition(name='example', description='test',
                                prompt_template='${CLAUDE_SKILL_DIR}: ${ARGUMENTS}',
                                skill_dir='/tmp/skill with spaces')
        self.assertEqual(resolve_skill_prompt(skill, None), '/tmp/skill with spaces: ')


if __name__ == '__main__':
    unittest.main()
