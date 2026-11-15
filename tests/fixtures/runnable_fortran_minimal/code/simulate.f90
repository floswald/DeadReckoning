program simulate
  implicit none
  integer :: i
  real :: total

  total = 0.0
  do i = 1, 10
     total = total + real(i)
  end do

  open(unit=10, file="result.txt", status="replace")
  write(10, '(F6.2)') total
  close(10)
end program simulate
