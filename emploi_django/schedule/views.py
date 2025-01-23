from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.generic import ListView
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ObjectDoesNotExist
import json
from .models import Course, Professor, Room, CourseAssignment, TimeSlot, Department, Semester
import logging

def select_department(request):
    """View for selecting department"""
    departments = Department.objects.all()
    return render(request, 'schedule/department_select.html', {'departments': departments})

def select_semester(request, department_code):
    """View for selecting semester within a department"""
    department = get_object_or_404(Department, code=department_code)
    semesters = Semester.objects.filter(department=department)
    if not semesters.exists():
        # Create semesters if they don't exist
        for code, _ in Semester.SEMESTER_CHOICES:
            Semester.objects.create(code=code, department=department)
        semesters = Semester.objects.filter(department=department)
    return render(request, 'schedule/semester_select.html', {
        'department': department,
        'semesters': semesters
    })

def view_schedule(request, department_code, semester_code):
    """View for displaying the weekly schedule"""
    department = get_object_or_404(Department, code=department_code)
    semester = get_object_or_404(Semester, department=department, code=semester_code)
    courses = Course.objects.filter(department=department, semester=semester)
    professors = Professor.objects.all()
    rooms = Room.objects.all()
    
    # Get all time slots for this department's courses
    course_assignments = CourseAssignment.objects.filter(course__in=courses)
    time_slots = TimeSlot.objects.filter(course_assignment__in=course_assignments)
    
    # Convert time slots to JSON for the schedule
    schedule_data = []
    for slot in time_slots:
        schedule_data.append({
            'day': slot.day,
            'period': slot.period,
            'week': slot.week,
            'course': slot.course_assignment.course.code,
            'professor': slot.course_assignment.professor.name,
            'type': slot.course_assignment.type,
            'room': slot.course_assignment.room.number if slot.course_assignment.room else ''
        })
    
    context = {
        'department': department,
        'semester': semester,
        'courses': courses,
        'professors': professors,
        'rooms': rooms,
        'schedule_data': json.dumps(schedule_data),
        'days': TimeSlot.DAYS,
        'periods': TimeSlot.PERIODS,
        'weeks': range(1, 17)
    }
    return render(request, 'schedule/schedule.html', context)

def view_plan(request, department_code, semester_code):
    """View for managing the schedule plan"""
    department = get_object_or_404(Department, code=department_code)
    semester = get_object_or_404(Semester, department=department, code=semester_code)
    courses = Course.objects.filter(department=department, semester=semester)
    
    # Update completion status for all courses
    for course in courses:
        course.update_completed_hours()
    
    context = {
        'department': department,
        'semester': semester,
        'courses': courses,
        'days': TimeSlot.DAYS,
        'periods': TimeSlot.PERIODS,
        'weeks': range(1, 17)
    }
    return render(request, 'schedule/plan.html', context)

class CourseListView(ListView):
    template_name = 'schedule/database.html'
    context_object_name = 'courses'

    def get_queryset(self):
        department_code = self.kwargs['department_code']
        semester_code = self.kwargs['semester_code']
        return Course.objects.filter(department__code=department_code, semester__code=semester_code)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department_code = self.kwargs['department_code']
        semester_code = self.kwargs['semester_code']
        department = get_object_or_404(Department, code=department_code)
        semester = get_object_or_404(Semester, department=department, code=semester_code)
        context['department'] = department
        context['semester'] = semester
        return context

# API Views
def get_courses(request, department_code, semester_code):
    """Get list of courses for a department and semester"""
    courses = Course.objects.filter(
        department__code=department_code,
        semester__code=semester_code
    ).values('code', 'title')
    return JsonResponse({'courses': list(courses)})

def get_course_info(request, department_code, semester_code, code):
    """Get, update, or delete course information"""
    try:
        if request.method == 'GET':
            course = Course.objects.get(pk=code, department__code=department_code, semester__code=semester_code)
            assignments = CourseAssignment.objects.filter(course=course)
            data = {
                'code': course.code,
                'title': course.title,
                'credits': course.credits,
                'cm_hours': course.cm_hours,
                'td_hours': course.td_hours,
                'tp_hours': course.tp_hours,
                'assignments': [{
                    'professor': assignment.professor.name,
                    'type': assignment.type,
                    'room': assignment.room.number if assignment.room else None
                } for assignment in assignments]
            }
            return JsonResponse(data)
            
        elif request.method == 'POST':
            data = json.loads(request.body)
            course, created = Course.objects.update_or_create(
                code=code,
                department__code=department_code,
                semester__code=semester_code,
                defaults={
                    'title': data['title'],
                    'credits': data['credits'],
                    'cm_hours': data['cm_hours'],
                    'td_hours': data['td_hours'],
                    'tp_hours': data['tp_hours']
                }
            )
            
            # Handle assignments
            CourseAssignment.objects.filter(course=course).delete()
            for assignment_data in data.get('assignments', []):
                professor = Professor.objects.get_or_create(name=assignment_data['professor'])[0]
                room = None
                if assignment_data.get('room'):
                    room = Room.objects.get_or_create(
                        number=assignment_data['room'],
                        defaults={'type': assignment_data['type']}
                    )[0]
                
                CourseAssignment.objects.create(
                    course=course,
                    professor=professor,
                    type=assignment_data['type'],
                    room=room
                )
            
            return JsonResponse({'status': 'success'})
            
        elif request.method == 'DELETE':
            course = Course.objects.get(pk=code, department__code=department_code, semester__code=semester_code)
            course.delete()
            return JsonResponse({'status': 'success'})
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_professors(request, department_code, semester_code):
    """Get all professors for a department and semester"""
    professors = Professor.objects.filter(courses__department__code=department_code, courses__semester__code=semester_code).distinct()
    data = [{'id': prof.id, 'name': prof.name} for prof in professors]
    return JsonResponse(data, safe=False)

def get_rooms(request, department_code, semester_code):
    """Get all rooms"""
    rooms = Room.objects.all()
    data = [{'id': room.id, 'number': room.number, 'type': room.type} for room in rooms]
    return JsonResponse(data, safe=False)

def get_schedule(request, department_code, semester_code, week):
    """Get schedule for a specific week"""
    slots = TimeSlot.objects.filter(
        course_assignment__course__department__code=department_code,
        course_assignment__course__semester__code=semester_code,
        week=week
    ).select_related('course_assignment', 'course_assignment__course', 'course_assignment__professor', 'course_assignment__room')
    
    schedule = []
    for slot in slots:
        schedule.append({
            'day': slot.day,
            'period': slot.period,
            'course': slot.course_assignment.course.code,
            'professor': slot.course_assignment.professor.name,
            'room': slot.course_assignment.room.number if slot.course_assignment.room else None,
            'type': slot.course_assignment.type
        })
    return JsonResponse({'schedule': schedule})

def get_all_plan(request, department_code, semester_code):
    """Get plan for all weeks"""
    slots = TimeSlot.objects.filter(
        course_assignment__course__department__code=department_code,
        course_assignment__course__semester__code=semester_code
    ).select_related(
        'course_assignment',
        'course_assignment__course'
    )
    
    data = []
    for slot in slots:
        data.append({
            'week': slot.week,
            'day': slot.day,
            'period': slot.period,
            'course_code': slot.course_assignment.course.code,
            'type': slot.course_assignment.type
        })
    return JsonResponse(data, safe=False)

def get_plan(request, department_code, semester_code, week):
    """Get plan for a specific week"""
    slots = TimeSlot.objects.filter(
        course_assignment__course__department__code=department_code,
        course_assignment__course__semester__code=semester_code,
        week=week
    ).select_related(
        'course_assignment',
        'course_assignment__course',
        'course_assignment__professor',
        'course_assignment__room'
    )
    
    plan = []
    for slot in slots:
        plan.append({
            'day': slot.day,
            'period': slot.period,
            'course_code': slot.course_assignment.course.code,
            'type': slot.course_assignment.type,
            'professor': slot.course_assignment.professor.name if slot.course_assignment.professor else None,
            'room': slot.course_assignment.room.number if slot.course_assignment.room else None
        })
    return JsonResponse(plan, safe=False)

@csrf_exempt
def save_plan(request, department_code, semester_code):
    """Save the planning data"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            department = get_object_or_404(Department, code=department_code)
            semester = get_object_or_404(Semester, department=department, code=semester_code)
            
            # Delete existing slots for this department and semester
            TimeSlot.objects.filter(
                course_assignment__course__department=department,
                course_assignment__course__semester=semester
            ).delete()
            
            # Create new slots
            for slot_data in data:
                course = Course.objects.get(
                    code=slot_data['course_code'],
                    department=department,
                    semester=semester
                )
                
                course_assignment = CourseAssignment.objects.get_or_create(
                    course=course,
                    type=slot_data['type']
                )[0]
                
                TimeSlot.objects.create(
                    course_assignment=course_assignment,
                    week=slot_data['week'],
                    day=slot_data['day'],
                    period=slot_data['period']
                )
            
            return JsonResponse({
                'status': 'success'
            })
            
        except Exception as e:
            return JsonResponse({
                'error': str(e)
            }, status=400)
    
    return JsonResponse({
        'error': 'Method not allowed'
    }, status=405)

@csrf_exempt
def update_course(request, department_code, semester_code):
    try:
        data = json.loads(request.body)
        code = data.get('code')
        updates = data.get('updates', {})
        
        course = Course.objects.get(code=code, department__code=department_code, semester__code=semester_code)
        
        # Update each field
        for field, value in updates.items():
            if hasattr(course, field):
                setattr(course, field, value)
        
        course.save()
        return JsonResponse({
            'status': 'success',
            'message': f'Course {code} updated successfully'
        })
        
    except Course.DoesNotExist:
        return JsonResponse({
            'error': f'Course with code {code} not found'
        }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=400)

@csrf_exempt
def delete_course(request, department_code, semester_code):
    """Delete a course"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code')
            
            if not code:
                return JsonResponse({
                    'error': 'Course code is required',
                    'status': 'error'
                })
            
            try:
                course = Course.objects.get(code=code, department__code=department_code, semester__code=semester_code)
                course_name = str(course)  # Save course info before deletion
                course.delete()
                
                return JsonResponse({
                    'message': f'Course {course_name} deleted successfully',
                    'status': 'success'
                })
                
            except Course.DoesNotExist:
                return JsonResponse({
                    'error': f'Course with code {code} not found',
                    'status': 'error'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'error': 'Invalid JSON data',
                'status': 'error'
            })
    
    return JsonResponse({
        'error': 'Invalid request method',
        'status': 'error'
    })

@csrf_exempt
def add_course(request, department_code, semester_code):
    """Add a new course to the database"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            department = get_object_or_404(Department, code=department_code)
            semester = get_object_or_404(Semester, department=department, code=semester_code)

            # Create the course
            course = Course.objects.create(
                code=data['code'],
                title=data['title'],
                credits=data['credits'],
                cm_hours=data['cm_hours'],
                td_hours=data['td_hours'],
                tp_hours=data['tp_hours'],
                department=department,
                semester=semester
            )

            # Create course assignments if professors are provided
            if data.get('cm_professor'):
                professor = Professor.objects.get_or_create(name=data['cm_professor'])[0]
                room = Room.objects.get_or_create(number=data['cm_room'])[0] if data.get('cm_room') else None
                CourseAssignment.objects.create(
                    course=course,
                    professor=professor,
                    type='CM',
                    room=room
                )

            if data.get('td_professor'):
                professor = Professor.objects.get_or_create(name=data['td_professor'])[0]
                CourseAssignment.objects.create(
                    course=course,
                    professor=professor,
                    type='TD'
                )

            if data.get('tp_professor'):
                professor = Professor.objects.get_or_create(name=data['tp_professor'])[0]
                room = Room.objects.get_or_create(number=data['tp_room'])[0] if data.get('tp_room') else None
                CourseAssignment.objects.create(
                    course=course,
                    professor=professor,
                    type='TP',
                    room=room
                )

            return JsonResponse({
                'success': True,
                'message': 'Course added successfully'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': str(e)
            }, status=400)

    return JsonResponse({
        'success': False,
        'message': 'Invalid request method'
    }, status=405)

@csrf_exempt
def save_slot(request, department_code, semester_code):
    """Save a time slot"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            department = get_object_or_404(Department, code=department_code)
            semester = get_object_or_404(Semester, department=department, code=semester_code)
            
            # Pour chaque slot
            for slot_data in data:
                # D'abord supprimer le slot existant s'il existe
                TimeSlot.objects.filter(
                    week=slot_data['week'],
                    day=slot_data['day'],
                    period=slot_data['period'],
                    course_assignment__course__department=department,
                    course_assignment__course__semester=semester
                ).delete()
                
                # Ensuite créer le nouveau slot
                course = Course.objects.get(
                    code=slot_data['course_code'],
                    department=department,
                    semester=semester
                )
                
                course_assignment = CourseAssignment.objects.get_or_create(
                    course=course,
                    type=slot_data['type']
                )[0]
                
                TimeSlot.objects.create(
                    course_assignment=course_assignment,
                    week=slot_data['week'],
                    day=slot_data['day'],
                    period=slot_data['period']
                )
            
            return JsonResponse({'status': 'success'})
            
        except Course.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Course not found'
            }, status=400)
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=405)

@csrf_exempt
def delete_slot(request, department_code, semester_code):
    """Delete a time slot"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            department = get_object_or_404(Department, code=department_code)
            semester = get_object_or_404(Semester, department=department, code=semester_code)
            
            # Find the time slot
            time_slot = TimeSlot.objects.get(
                course_assignment__course__department=department,
                course_assignment__course__semester=semester,
                week=data['week'],
                day=data['day'],
                period=data['period']
            )
            
            # Delete the time slot
            time_slot.delete()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Time slot deleted successfully'
            })
            
        except TimeSlot.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Time slot not found'
            }, status=404)
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method'
    }, status=405)

def view_bilan(request, department_code, semester_code):
    """View for displaying the course progress"""
    try:
        department = get_object_or_404(Department, code=department_code)
        semester = get_object_or_404(Semester, department=department, code=semester_code)
        courses = Course.objects.filter(department=department, semester=semester)
        
        context = {
            'department': department,
            'semester': semester,
            'courses': courses,
        }
        return render(request, 'schedule/bilan.html', context)
    except Exception as e:
        logger.error(f"Error in bilan_view: {str(e)}")
        return render(request, 'schedule/bilan.html', {
            'courses': [],
            'error_message': "Une erreur s'est produite lors du chargement des données.",
            'department': get_object_or_404(Department, code=department_code),
            'semester': get_object_or_404(Semester, department=get_object_or_404(Department, code=department_code), code=semester_code),
        })

@csrf_exempt
def update_bilan(request, department_code, semester_code):
    """Update course completion values"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    try:
        course_code = data.get('course_code')
        field = data.get('field')
        value = data.get('value')
        
        # Validate required fields
        if not all([course_code, field, value is not None]):
            return JsonResponse({
                'error': 'Missing required fields'
            }, status=400)
        
        # Validate field name
        valid_fields = ['cm_completed', 'td_completed', 'tp_completed']
        if field not in valid_fields:
            return JsonResponse({
                'error': f'Invalid field name. Must be one of: {", ".join(valid_fields)}'
            }, status=400)
        
        try:
            value = float(value)
        except (TypeError, ValueError):
            return JsonResponse({'error': str(e)}, status=400)

        # Get and update course
        course = Course.objects.get(code=course_code, department__code=department_code, semester__code=semester_code)
        
        # Validate against planned hours
        planned_hours = getattr(course, field.replace('completed', 'hours'))
        if value > planned_hours:
            return JsonResponse({
                'error': f'Completed hours ({value}) cannot exceed planned hours ({planned_hours})'
            }, status=400)
        
        # Update the field
        setattr(course, field, value)
        course.save()
        
        # Return updated progress values
        return JsonResponse({
            'status': 'success',
            'progress': {
                'cm': course.progress_cm(),
                'td': course.progress_td(),
                'tp': course.progress_tp(),
                'total': course.total_progress()
            }
        })
        
    except Course.DoesNotExist:
        return JsonResponse({
            'error': f'Course with code {course_code} not found'
        }, status=404)
        
    except Exception as e:
        logger.error(f"Error in update_bilan: {str(e)}")
        return JsonResponse({'error': 'Server error'}, status=500)