from teacher import Teacher


def test_teacher_configuration_initializes_without_provider_call():
    teacher = Teacher()

    assert teacher is not None
    assert isinstance(teacher.model, str)
    assert teacher.model
