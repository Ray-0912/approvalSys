from database.CI_API_Client import APIClient


testClient = APIClient()


def testadd(pin):
    try:
        newp = testClient.create_person(pin=pin, name='test', organization_unit_id=8)
        print("人員資訊:", newp)
        return 1
        # print(testClient.get_persons("8,13"))
    except Exception as e:
        print("取得人員資訊時發生錯誤:", e)
        return 0

if __name__ == "__main__":
    # t = testClient.get_latest_person_pin(8)
    a = 'aa'
    b = 'bb'
    print(a+b)



