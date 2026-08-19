package com.settleagent.backend.user;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserRepository extends JpaRepository<UserEntity, String> {

    Optional<UserEntity> findByEmail(String email);

    boolean existsByEmail(String email);

    boolean existsByNickname(String nickname);
}
