from typing import Annotated
from datetime import datetime
from collections import defaultdict

import strawberry
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from strawberry.fastapi import BaseContext, GraphQLRouter
from strawberry.types import Info
from strawberry.permission import BasePermission
from auth import get_optional_user, can_access_student
from strawberry.dataloader import DataLoader
from graphql import GraphQLError
from strawberry.extensions import DisableIntrospection, MaskErrors, MaxAliasesLimiter, QueryDepthLimiter

from db import get_db
from models import Course, Enrollment, Student, User
import services
from config import settings


def check_limit(limit: int) -> int:
    if not 1 <= limit <= 100:
        raise GraphQLError("limit must be between 1 and 100")
    return limit


def parse_id(value: strawberry.ID) -> int:
    try:
        return int(value)
    except ValueError:
        raise GraphQLError(f"Invalid ID: {value!r}") from None


def should_mask(error: GraphQLError) -> bool:
    original = error.original_error
    return original is not None and not isinstance(original, GraphQLError)


def batch_loader(db: Session, column, many: bool = False) -> DataLoader:
    """Preserve input key order, including missing keys and empty relations."""
    model = column.class_

    async def load(keys: list) -> list:
        rows = db.scalars(select(model).where(column.in_(keys)).order_by(model.id)).all()
        groups = defaultdict(list)
        for row in rows:
            groups[getattr(row, column.key)].append(row)
        if many:
            return [groups[key] for key in keys]
        return [groups[key][0] if groups[key] else None for key in keys]

    return DataLoader(load_fn=load)


class Context(BaseContext):
    def __init__(self, db: Session, user: User | None = None):
        super().__init__()
        self.db = db
        self.user = user
        self.course_loader = batch_loader(db, Course.id)
        self.student_loader = batch_loader(db, Student.id)
        self.student_enrollments_loader = batch_loader(db, Enrollment.student_id, many=True)
        self.course_enrollments_loader = batch_loader(db, Enrollment.course_id, many=True)

    def clear_loaders(self) -> None:
        # Mutations in the same request must not see stale cached relationships.
        for loader in (self.course_loader, self.student_loader,
                       self.student_enrollments_loader, self.course_enrollments_loader):
            loader.clear_all()


def get_context(db: Annotated[Session, Depends(get_db)],
                user: Annotated[User | None, Depends(get_optional_user)]) -> Context:
    return Context(db, user)


class IsAuthenticated(BasePermission):
    message = "Authentication required"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        return info.context.user is not None


class IsAdmin(BasePermission):
    message = "Admin role required"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        return info.context.user is not None and info.context.user.role == "admin"


class IsSelfOrAdmin(BasePermission):
    message = "Not allowed to read this field"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        user = info.context.user
        return user is not None and can_access_student(user, int(source.id))


@strawberry.type(name="Course")
class CourseType:
    id: strawberry.ID
    title: str
    description: str
    credits: int
    is_elective: bool
    likes: int
    level: str
    @strawberry.field
    async def enrollments(self, info: Info) -> list["EnrollmentType"]:
        return await info.context.course_enrollments_loader.load(self.id)


@strawberry.type(name="Student")
class StudentType:
    id: strawberry.ID
    name: str
    email: str | None = strawberry.field(permission_classes=[IsSelfOrAdmin])
    @strawberry.field
    async def enrollments(self, info: Info) -> list["EnrollmentType"]:
        return await info.context.student_enrollments_loader.load(int(self.id))


@strawberry.type(name="Enrollment")
class EnrollmentType:
    id: strawberry.ID
    enrolled_at: datetime
    course_id: strawberry.Private[str]
    student_id: strawberry.Private[int]

    @strawberry.field
    async def course(self, info: Info) -> CourseType:
        return await info.context.course_loader.load(self.course_id)

    @strawberry.field
    async def student(self, info: Info) -> StudentType:
        return await info.context.student_loader.load(self.student_id)


@strawberry.type(name="User")
class UserType:
    id: strawberry.ID
    email: str
    role: str
    student_id: int | None


@strawberry.type
class Query:
    @strawberry.field(permission_classes=[IsAuthenticated])
    def me(self, info: Info) -> UserType:
        return info.context.user

    @strawberry.field
    def courses(self, info: Info, is_elective: bool | None = None,
                limit: int = 20) -> list[CourseType]:
        stmt = select(Course).order_by(Course.likes.desc(), Course.id).limit(check_limit(limit))
        if is_elective is not None:
            stmt = stmt.where(Course.is_elective == is_elective)
        return info.context.db.scalars(stmt).all()

    @strawberry.field
    def course(self, info: Info, id: strawberry.ID) -> CourseType | None:
        return info.context.db.get(Course, id)

    @strawberry.field(permission_classes=[IsAdmin])
    def students(self, info: Info, limit: int = 20) -> list[StudentType]:
        return info.context.db.scalars(select(Student).order_by(Student.id).limit(check_limit(limit))).all()

    @strawberry.field
    def student(self, info: Info, id: strawberry.ID) -> StudentType | None:
        return info.context.db.get(Student, parse_id(id))

    @strawberry.field
    def enrollments(self, info: Info, limit: int = 20) -> list[EnrollmentType]:
        return info.context.db.scalars(select(Enrollment).order_by(Enrollment.id).limit(check_limit(limit))).all()


@strawberry.type
class UserError:
    code: str
    message: str


@strawberry.input
class EnrollInput:
    course_id: strawberry.ID
    student_id: strawberry.ID


@strawberry.type
class EnrollPayload:
    enrollment: EnrollmentType | None = None
    user_errors: list[UserError] = strawberry.field(default_factory=list)


@strawberry.type
class LikePayload:
    course: CourseType | None = None
    user_errors: list[UserError] = strawberry.field(default_factory=list)


def as_user_errors(err: services.ServiceError) -> list[UserError]:
    return [UserError(code=err.code, message=err.message)]


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def enroll(self, info: Info, input: EnrollInput) -> EnrollPayload:
        student_id = parse_id(input.student_id)
        if not can_access_student(info.context.user, student_id):
            raise GraphQLError("You can enroll only yourself")
        try:
            enrollment = services.enroll(info.context.db, input.course_id, student_id)
        except services.ServiceError as err:
            return EnrollPayload(user_errors=as_user_errors(err))
        info.context.clear_loaders()
        return EnrollPayload(enrollment=enrollment)

    @strawberry.mutation
    def like_course(self, info: Info, id: strawberry.ID) -> LikePayload:
        try:
            course = services.like_course(info.context.db, id)
        except services.ServiceError as err:
            return LikePayload(user_errors=as_user_errors(err))
        info.context.clear_loaders()
        return LikePayload(course=course)


extensions = [
    lambda: QueryDepthLimiter(max_depth=5),
    lambda: MaxAliasesLimiter(max_alias_count=10),
    lambda: MaskErrors(should_mask_error=should_mask),
]
if not settings.graphql_introspection:
    extensions.append(DisableIntrospection)

schema = strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)
graphql_app = GraphQLRouter(schema, context_getter=get_context)
