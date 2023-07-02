# Team: 0= Management, 1= Accounting, 2= FrontDesk, 3= HouseKeeping, 4= Works, 99= SysSupervisor
# Role: 0= Director, 1= Manager, 2= Mid-Manager, 3= Staff, 99= SysSupervisor


def has_permission(page, user_id, user_team, user_role):
    if user_id == 1:
        return True

    if page == 'reset_password':
        if user_id == 1:
            return True
    elif page == 'p_list' or page == 'p_edit' or page == 'p_new' or page == 'p_view':
        if user_role == 0 or user_role == 1:
            return True

    return False
