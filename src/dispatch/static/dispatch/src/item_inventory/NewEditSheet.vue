<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Item Inventory</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading"
            :disabled="invalid || !validated"
            @click="submitSaveLocal()"
          >
            <v-icon>save</v-icon>
          </v-btn>
          <v-btn icon color="secondary" @click="closeCreateEdit()">
            <v-icon>close</v-icon>
          </v-btn>
        </v-list-item>
      </template>
      <v-card flat>
        <v-card-text>
          <v-container grid-list-md>
            <v-layout wrap>
              <v-flex xs12>
                <span class="subtitle-2">Item Inventory Details</span>
              </v-flex>
              <v-flex xs12>
                <DepotCombobox v-model="depot" label="Depot" rules="required" />
              </v-flex>
              <v-flex xs12>
                <ItemCombobox v-model="item" label="Item" rules="required" />
              </v-flex>
              <v-flex xs12>
                <ValidationProvider name="MaxQty" rules="required" immediate>
                  <v-text-field
                    v-model="max_qty"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Max Quantity"
                    type="number"
                    hint="A max_qty for your depot."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>

              <v-flex xs12>
                <ValidationProvider name="Qty" rules="required" immediate>
                  <v-text-field
                    v-model="curr_qty"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Quantity"
                    type="number"
                    hint="The quantity for this item in this depot."
                    clearable
                    required
                  />
                </ValidationProvider>
              </v-flex>

              <v-flex xs12>
                <ValidationProvider name="allocated_qty" rules="required" immediate>
                  <v-text-field
                    v-model="allocated_qty"
                    slot-scope="{ errors, valid }"
                    :error-messages="errors"
                    :success="valid"
                    label="Allocated Quantity"
                    type="number"
                    hint="The quantity for this item in this depot."
                  />
                </ValidationProvider>
              </v-flex>
            </v-layout>
          </v-container>
        </v-card-text>
      </v-card>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { required } from "vee-validate/dist/rules";
import ItemCombobox from "@/item/Combobox.vue";
import DepotCombobox from "@/depot/Combobox.vue";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "ItemInventoryNewEditSheet",

  components: {
    ValidationObserver,
    ValidationProvider,
    ItemCombobox,
    DepotCombobox,
  },
  data() {
    let today = new Date();
    let env_start_day = today.toISOString().split("T")[0].replace(/-/g, "");
    return {
      tab: null,
      localFlexFormData: {},
    };
  },
  computed: {
    ...mapFields("item_inventory", [
      "selected.id",
      "selected.max_qty",
      "selected.allocated_qty",
      "selected.curr_qty",
      "selected.depot",
      "selected.item",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
  },

  methods: {
    ...mapActions("item_inventory", [
      "save",
      "closeCreateEdit",
      "setSelectedFormDataAndSave",
    ]),
    submitSaveLocal() {
      this.setSelectedFormDataAndSave({});
    },
  },
};
</script>
