<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-card class="mx-auto" max-width="500" style="margin-top: -64px;">
      <v-card-title>Login to EasyDispatch</v-card-title>
      <v-card-text>
        <v-form>
          <v-container>
            <v-row>
              <v-col cols="12" md="12">
                <ValidationProvider name="Eamil" rules="required|email" immediate>
                  <v-text-field
                    v-model="email"
                    label="Email"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    required
                  ></v-text-field>
                </ValidationProvider>
              </v-col>
              <v-col cols="12" md="12">
                <ValidationProvider name="Password" rules="required" immediate>
                  <v-text-field
                    v-model="password"
                    :type="'password'"
                    label="Password"
                    slot-scope="{ errors, valid }"
                    :success="valid"
                    :error-messages="errors"
                    required
                  ></v-text-field>
                </ValidationProvider>
              </v-col>
            </v-row>
          </v-container>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-list-item>
          <v-row align="center" justify="end">
            <v-btn color="primary" @click="goRegister()">Register</v-btn>
            <v-spacer />
            <v-btn color="primary" @click="basicLogin({ email: email, password: password })">Login</v-btn>
          </v-row>
        </v-list-item>
      </v-card-actions>
    </v-card>
  </ValidationObserver>
</template>

<script>
//disabled
import { mapActions } from "vuex";

import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required, email } from "vee-validate/dist/rules";
extend("email", email);

extend("required", {
  ...required,
  message: "This field is required",
});
export default {
  components: {
    ValidationProvider,
    ValidationObserver,
  },
  data() {
    return {
      email: "",
      password: "",
    };
  },
  methods: {
    goRegister() {
      this.$router.push({ path: "register" });
    },
    ...mapActions("auth", ["basicLogin"]),
  },
};
</script>

<style scoped></style>
