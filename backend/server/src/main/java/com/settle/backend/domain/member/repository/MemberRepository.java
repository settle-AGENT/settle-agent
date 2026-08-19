package com.settle.backend.domain.member.repository;

import com.settle.backend.domain.member.entity.Member;
import java.util.Optional;

public interface MemberRepository {

    Member save(Member member);

    Optional<Member> findByEmail(String email);
}
